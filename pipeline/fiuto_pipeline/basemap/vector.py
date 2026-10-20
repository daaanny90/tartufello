"""Layer vettoriali della basemap offline e PMTiles a più layer.

Il driver PMTiles di GDAL (via pyogrio) scrive un solo layer per file: non
aggiunge layer a un PMTiles esistente. Quindi si scrive un PMTiles per "parte"
e poi si uniscono i tile. Un tile MVT è una sequenza di messaggi Layer, per cui
concatenare i byte (decompressi) di due tile dà un tile con i layer di entrambi.

Vincolo: in un tile un nome di layer deve comparire una volta sola. Due parti
con lo stesso layer devono avere zoom disgiunti (es. curve maggiori z10-12 e
tutte le curve z13-15). `check_parts` e `merge_pmtiles` lo controllano.
"""

from __future__ import annotations

import gzip
import os
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import FiutoError

# Tipi della rete stradale DBTR -> kind (vedi sources.toml, [sources.dbtr]).
ROAD_KIND_STRADA = "strada"
ROAD_KIND_CARRARECCIA = "carrareccia"
ROAD_KIND_SENTIERO = "sentiero"


@dataclass
class Part:
    """Un layer (o una fascia di zoom di un layer) da scrivere nella basemap."""

    layer: str
    gdf: object  # GeoDataFrame in EPSG:4326
    minzoom: int
    maxzoom: int
    description: str = ""
    extra: dict = field(default_factory=dict)


def check_parts(parts: list[Part]) -> None:
    """Le parti con lo stesso layer non devono condividere zoom."""
    seen: dict[str, list[tuple[int, int]]] = {}
    for p in parts:
        if p.minzoom > p.maxzoom:
            raise ValueError(f"layer {p.layer}: minzoom {p.minzoom} > maxzoom {p.maxzoom}")
        for lo, hi in seen.get(p.layer, []):
            if p.minzoom <= hi and lo <= p.maxzoom:
                raise ValueError(
                    f"layer {p.layer}: zoom {p.minzoom}-{p.maxzoom} sovrapposti a {lo}-{hi} "
                    "(in un tile un layer può comparire una volta sola)"
                )
        seen.setdefault(p.layer, []).append((p.minzoom, p.maxzoom))


def zoom_split(layer: str, gdf, keep_low, *, minzoom: int, split: int, maxzoom: int, description: str = ""):
    """Due parti dello stesso layer: sotto `split` solo le righe con keep_low True, da `split` tutte."""
    return [
        Part(layer, gdf[keep_low].copy(), minzoom, split - 1, description),
        Part(layer, gdf, split, maxzoom, description),
    ]


# --- costruzione dei layer -------------------------------------------------------------


def _present(geoms):
    """True dove la geometria c'è e non è vuota (senza l'avviso di GeoSeries.notna)."""
    import shapely

    arr = getattr(geoms, "values", geoms)
    return ~shapely.is_missing(arr) & ~shapely.is_empty(arr)


def _explode_lines(gdf):
    """Solo LineString (le MultiLineString si spezzano), senza geometrie vuote."""
    gdf = gdf[_present(gdf.geometry)]
    gdf = gdf.explode(index_parts=False, ignore_index=True)
    return gdf[gdf.geom_type == "LineString"].reset_index(drop=True)


def clip_wgs84(gdf, bbox: tuple[float, float, float, float]):
    """Ritaglia sul bbox lon/lat (le feature WFS/REST arrivano intere anche se escono dall'AOI)."""
    import shapely

    if gdf.empty:
        return gdf
    out = gdf.copy()
    out = out.set_geometry(shapely.clip_by_rect(out.geometry.values, *bbox))
    return out[_present(out.geometry)].reset_index(drop=True)


def _text(series):
    """Testo pulito; vuoto o solo spazi -> None (la proprietà non si scrive)."""

    import pandas as pd

    def clean(v):
        if v is None or (not isinstance(v, str) and pd.isna(v)):
            return None
        s = str(v).strip()
        return s or None

    return series.map(clean).astype("object")


def contours_gdf(lines: list[tuple[int, bool, object]], crs: str):
    """Curve [(quota, maggiore, LineString)] -> GeoDataFrame EPSG:4326 con ele (int) e major (bool)."""
    import geopandas as gpd
    import pandas as pd

    gdf = gpd.GeoDataFrame(
        {
            "ele": pd.array([e for e, _, _ in lines], dtype="int32"),
            "major": pd.array([m for _, m, _ in lines], dtype="bool"),
        },
        geometry=[g for _, _, g in lines],
        crs=crs,
    )
    return gdf.to_crs("EPSG:4326")


def trails_gdf(raw, *, name_attr: str, ref_attr: str, kind_attr: str, difficulty_attr: str):
    """Percorsi della rete escursionistica -> name, ref, kind, difficulty."""
    import geopandas as gpd

    gdf = _explode_lines(raw.to_crs("EPSG:4326"))
    out = gpd.GeoDataFrame(
        {
            "name": _text(gdf[name_attr]),
            "ref": _text(gdf[ref_attr]),
            "kind": _text(gdf[kind_attr]),
            "difficulty": _text(gdf[difficulty_attr]),
        },
        geometry=gdf.geometry.values,
        crs="EPSG:4326",
    )
    return out


def roads_gdf(by_kind: dict[str, object]):
    """{kind: GeoDataFrame} -> un layer con la sola proprietà kind."""
    import geopandas as gpd
    import pandas as pd

    frames = []
    for kind, g in by_kind.items():
        if g is None or g.empty:
            continue
        g = _explode_lines(g.to_crs("EPSG:4326"))
        frames.append(
            gpd.GeoDataFrame({"kind": [kind] * len(g)}, geometry=g.geometry.values, crs="EPSG:4326")
        )
    if not frames:
        return gpd.GeoDataFrame({"kind": []}, geometry=[], crs="EPSG:4326")
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")


def water_gdf(raw, *, name_attr: str):
    import geopandas as gpd

    gdf = _explode_lines(raw.to_crs("EPSG:4326"))
    return gpd.GeoDataFrame({"name": _text(gdf[name_attr])}, geometry=gdf.geometry.values, crs="EPSG:4326")


def places_gdf(raw, *, name_attr: str, kind_attr: str):
    import geopandas as gpd

    gdf = raw.to_crs("EPSG:4326")
    gdf = gdf[gdf.geom_type == "Point"].reset_index(drop=True)
    out = gpd.GeoDataFrame(
        {"name": _text(gdf[name_attr]), "kind": _text(gdf[kind_attr])},
        geometry=gdf.geometry.values,
        crs="EPSG:4326",
    )
    return out[out["name"].notna()].reset_index(drop=True)


# --- scrittura e unione dei PMTiles ---------------------------------------------------


def write_part(part: Part, path: Path, *, simplification: float | None = None) -> Path | None:
    """Un PMTiles con un solo layer (driver GDAL). Nessun file se la parte è vuota."""
    import pyogrio

    if part.gdf is None or part.gdf.empty:
        return None
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    opts = {
        "MINZOOM": str(part.minzoom),
        "MAXZOOM": str(part.maxzoom),
        "NAME": part.layer,
        "DESCRIPTION": part.description,
    }
    if simplification is not None:
        opts["SIMPLIFICATION"] = str(simplification)
    pyogrio.write_dataframe(part.gdf, path, driver="PMTiles", layer=part.layer, dataset_options=opts)
    return path


def _merge_vector_layers(acc: dict[str, dict], layers: list[dict]) -> None:
    for vl in layers or []:
        lid = vl.get("id")
        if not lid:
            continue
        cur = acc.setdefault(lid, {"id": lid, "description": vl.get("description", ""), "fields": {}})
        cur["fields"].update(vl.get("fields") or {})
        for k, fn in (("minzoom", min), ("maxzoom", max)):
            if k in vl:
                cur[k] = fn(cur[k], vl[k]) if k in cur else vl[k]
        if vl.get("description") and not cur.get("description"):
            cur["description"] = vl["description"]


def merge_pmtiles(
    paths: list[Path], out: Path, metadata: dict, layer_descriptions: dict[str, str] | None = None
) -> dict:
    """Unisce PMTiles vettoriali (MVT) tile per tile. Ritorna header e conteggi del file scritto.

    Ogni tile risultante è gzip; metadata = `metadata` + vector_layers, bounds, center, zoom.
    """
    from pmtiles.reader import MmapSource, Reader, all_tiles
    from pmtiles.tile import Compression, TileType, zxy_to_tileid
    from pmtiles.writer import Writer

    from ..export.mvt import layer_names

    if not paths:
        raise FiutoError("nessun layer da unire: tutte le parti sono vuote")
    tiles: dict[int, list[bytes]] = {}
    vlayers: dict[str, dict] = {}
    minz, maxz = 99, -1
    lon0, lat0, lon1, lat1 = 180e7, 90e7, -180e7, -90e7
    for p in paths:
        with open(p, "rb") as f:
            src = MmapSource(f)
            reader = Reader(src)
            h = reader.header()
            if h["tile_type"] != TileType.MVT:
                raise FiutoError(f"{p}: non è un PMTiles vettoriale (MVT)")
            meta = reader.metadata()
            _merge_vector_layers(vlayers, meta.get("vector_layers", []))
            minz, maxz = min(minz, h["min_zoom"]), max(maxz, h["max_zoom"])
            lon0, lat0 = min(lon0, h["min_lon_e7"]), min(lat0, h["min_lat_e7"])
            lon1, lat1 = max(lon1, h["max_lon_e7"]), max(lat1, h["max_lat_e7"])
            for zxy, data in all_tiles(src):
                if data[:2] == b"\x1f\x8b":
                    data = gzip.decompress(data)
                tiles.setdefault(zxy_to_tileid(*zxy), []).append(data)
    for lid, desc in (layer_descriptions or {}).items():
        if lid in vlayers and desc:
            vlayers[lid]["description"] = desc

    header = {
        "tile_type": TileType.MVT,
        "tile_compression": Compression.GZIP,
        "min_zoom": minz,
        "max_zoom": maxz,
        "min_lon_e7": int(lon0),
        "min_lat_e7": int(lat0),
        "max_lon_e7": int(lon1),
        "max_lat_e7": int(lat1),
        "center_zoom": minz,
        "center_lon_e7": int((lon0 + lon1) / 2),
        "center_lat_e7": int((lat0 + lat1) / 2),
    }
    bounds = [lon0 / 1e7, lat0 / 1e7, lon1 / 1e7, lat1 / 1e7]
    meta = {
        **metadata,
        "format": "pbf",
        "minzoom": minz,
        "maxzoom": maxz,
        "bounds": ",".join(f"{v:.7f}" for v in bounds),
        "center": f"{(bounds[0] + bounds[2]) / 2:.7f},{(bounds[1] + bounds[3]) / 2:.7f},{minz}",
        "vector_layers": [vlayers[k] for k in sorted(vlayers)],
    }

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    per_layer: dict[str, int] = {}
    with open(tmp, "wb") as f:
        w = Writer(f)
        for tid in sorted(tiles):
            data = b"".join(tiles[tid])
            names = layer_names(data)
            if len(names) != len(set(names)):
                raise FiutoError(f"tile {tid}: layer ripetuti {names} (zoom sovrapposti tra le parti?)")
            for n in names:
                per_layer[n] = per_layer.get(n, 0) + 1
            w.write_tile(tid, gzip.compress(data, compresslevel=9, mtime=0))
        w.finalize(header, meta)
    os.replace(tmp, out)
    return {
        "path": str(out),
        "bytes": out.stat().st_size,
        "tiles": len(tiles),
        "min_zoom": minz,
        "max_zoom": maxz,
        "tiles_per_layer": per_layer,
        "vector_layers": meta["vector_layers"],
    }
