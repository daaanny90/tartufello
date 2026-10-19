"""Scrittura di GeoJSONSeq (EPSG:4326) e PMTiles vettoriale (layer `vth`).

Strada principale: driver PMTiles di GDAL (>= 3.8) via pyogrio, che proietta
in EPSG:3857 e taglia i tile. Il driver non accetta chiavi di metadata
arbitrarie (solo NAME, DESCRIPTION, TYPE...), quindi dopo la scrittura il file
viene riscritto con il pacchetto `pmtiles` aggiungendo model, built, aoi,
sources (contratto tiles.metadata). I tile restano byte per byte gli stessi.

Ripiego 1: driver MBTiles di GDAL + conversione con `pmtiles`.
Ripiego 2: solo GeoJSONSeq, poi tippecanoe o go-pmtiles a mano (vedi README).
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path

import pyogrio

from ..errors import FiutoError
from .polygonize import contract_keys, feature_properties

METHOD_GDAL_PMTILES = "gdal-pmtiles"
METHOD_GDAL_MBTILES = "gdal-mbtiles+pmtiles-convert"
METHOD_NONE = "solo-geojsonseq"


def available_method() -> str:
    drivers = pyogrio.list_drivers()
    if "w" in drivers.get("PMTiles", ""):
        return METHOD_GDAL_PMTILES
    if "w" in drivers.get("MBTiles", ""):
        return METHOD_GDAL_MBTILES
    return METHOD_NONE


def write_geojsonseq(gdf_wgs84, path: Path, keys: list[str]) -> Path:
    """Una feature GeoJSON per riga (RFC 8142 senza separatore RS), chiavi NA omesse."""
    from shapely.geometry import mapping

    path.parent.mkdir(parents=True, exist_ok=True)
    cols = [k for k in keys if k in gdf_wgs84.columns]
    with open(path, "w", encoding="utf-8") as f:
        for row, geom in zip(gdf_wgs84[cols].to_dict("records"), gdf_wgs84.geometry):
            feat = {"type": "Feature", "properties": feature_properties(row, cols), "geometry": mapping(geom)}
            f.write(json.dumps(feat, separators=(",", ":")) + "\n")
    return path


def _for_ogr(gdf_wgs84, keys: list[str]):
    """Tipi adatti a OGR: interi nullable restano Int32, score float64 con NaN = nullo."""
    cols = [k for k in keys if k in gdf_wgs84.columns]
    out = gdf_wgs84[cols + [gdf_wgs84.geometry.name]].copy()
    if "score" in out.columns:
        out["score"] = out["score"].astype("float64")
    return out


def _dataset_options(minzoom, maxzoom, name, description, simplification, simplification_max_zoom):
    opts = {"MINZOOM": str(minzoom), "MAXZOOM": str(maxzoom), "NAME": name, "DESCRIPTION": description}
    if simplification is not None:
        opts["SIMPLIFICATION"] = str(simplification)
    if simplification_max_zoom is not None:
        opts["SIMPLIFICATION_MAX_ZOOM"] = str(simplification_max_zoom)
    return opts


def set_pmtiles_metadata(path: Path, extra: dict) -> dict:
    """Riscrive il PMTiles con metadata = metadata esistente + `extra`.

    Se il metadata arriva da MBTiles (chiave "json" con vector_layers in
    stringa), lo porta al livello superiore come vuole PMTiles v3.
    """
    from pmtiles.reader import MmapSource, Reader, all_tiles
    from pmtiles.tile import zxy_to_tileid
    from pmtiles.writer import Writer

    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(path, "rb") as f:
        src = MmapSource(f)
        reader = Reader(src)
        header = reader.header()
        meta = reader.metadata()
        if isinstance(meta.get("json"), str):
            try:
                meta.update(json.loads(meta.pop("json")))
            except json.JSONDecodeError:
                pass
        meta.update(extra)
        tiles = sorted(((zxy_to_tileid(*zxy), data) for zxy, data in all_tiles(src)), key=lambda t: t[0])
        if not tiles:
            raise FiutoError(f"{path}: nessun tile scritto (geometrie vuote o fuori zoom?)")
        with open(tmp, "wb") as out:
            w = Writer(out)
            for tid, data in tiles:
                w.write_tile(tid, data)
            w.finalize(header, meta)
    os.replace(tmp, path)
    return meta


def write_pmtiles(
    gdf_wgs84,
    path: Path,
    *,
    keys: list[str],
    layer: str,
    minzoom: int,
    maxzoom: int,
    name: str,
    description: str,
    metadata: dict,
    simplification: float | None = None,
    simplification_max_zoom: float | None = None,
    method: str | None = None,
) -> dict:
    """Scrive il PMTiles vettoriale e aggiunge il metadata del contratto.

    Ritorna {"method", "gdal", "path"}; con METHOD_NONE non scrive nulla.
    """
    method = method or available_method()
    info = {"method": method, "gdal": pyogrio.__gdal_version_string__, "path": None}
    if method == METHOD_NONE:
        return info
    if gdf_wgs84.empty:
        raise FiutoError("nessun poligono da esportare: maschera vuota o nessun dato")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    data = _for_ogr(gdf_wgs84, keys)
    opts = _dataset_options(minzoom, maxzoom, name, description, simplification, simplification_max_zoom)

    if method == METHOD_GDAL_PMTILES:
        pyogrio.write_dataframe(data, path, driver="PMTiles", layer=layer, dataset_options=opts)
    elif method == METHOD_GDAL_MBTILES:
        from pmtiles.convert import mbtiles_to_pmtiles

        with tempfile.TemporaryDirectory() as td:
            mb = Path(td) / "vth.mbtiles"
            pyogrio.write_dataframe(data, mb, driver="MBTiles", layer=layer, dataset_options=opts)
            _check_mbtiles(mb)
            mbtiles_to_pmtiles(str(mb), str(path), maxzoom)
    else:
        raise ValueError(f"metodo sconosciuto: {method}")

    set_pmtiles_metadata(path, metadata)
    info["path"] = str(path)
    return info


def _check_mbtiles(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        n = conn.execute("SELECT count(*) FROM tiles").fetchone()[0]
    if n == 0:
        raise FiutoError(f"{path}: MBTiles senza tile")


def tippecanoe_hint(geojsonseq: Path, out: Path, layer: str, minzoom: int, maxzoom: int) -> str:
    return (
        "GDAL senza driver PMTiles/MBTiles in scrittura. Converti a mano, ad esempio:\n"
        f"  tippecanoe -o {out} -l {layer} -Z {minzoom} -z {maxzoom} "
        f"--detect-shared-borders --coalesce-densest-as-needed {geojsonseq}\n"
        "Il metadata (model, built, aoi, sources) poi va aggiunto: è nel report.json del build."
    )


__all__ = [
    "METHOD_GDAL_MBTILES",
    "METHOD_GDAL_PMTILES",
    "METHOD_NONE",
    "available_method",
    "contract_keys",
    "set_pmtiles_metadata",
    "tippecanoe_hint",
    "write_geojsonseq",
    "write_pmtiles",
]
