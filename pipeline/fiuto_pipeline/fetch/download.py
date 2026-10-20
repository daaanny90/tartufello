"""Scaricatori con cache locale in data/raw/<sorgente>/.

- url: un file (zip compresi) da endpoints.download
- wfs: GetFeature a pagine sul bbox dell'AOI, poi un unico GPKG
- wcs: GetCoverage 2.0.1 a riquadri sul bbox dell'AOI (cartella di GeoTIFF)

Tutti rifiutano di partire se mancano gli identificativi in sources.toml.
A fine download scrivono data/raw/<sorgente>/fetched.json: il build usa quel
file se local_path è vuoto.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, UTC
from pathlib import Path

from ..config import MANIFEST_NAME, Source
from ..errors import ConfigError, FiutoError, NotConfigured
from . import ows
from .http import filename_from, get, looks_like_xml, save_stream, session

GEODATA_EXT = {".shp", ".gpkg", ".geojson", ".json", ".gml", ".tif", ".tiff", ".asc", ".img", ".vrt", ".kml"}
METHODS = ("url", "wfs", "wcs")


def write_manifest(src: Source, path: Path | None, **extra) -> Path:
    src.cache_dir.mkdir(parents=True, exist_ok=True)
    man = {
        "source": src.id,
        "path": str(path) if path else None,
        "fetched": datetime.now(UTC).isoformat(timespec="seconds"),
        **extra,
    }
    p = src.cache_dir / MANIFEST_NAME
    p.write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def choose_method(src: Source, method: str | None) -> str:
    if method:
        if method not in METHODS:
            raise ConfigError(f"metodo '{method}' non valido (ammessi: {', '.join(METHODS)})")
        return method
    if src.endpoint("download"):
        return "url"
    if src.endpoint("wfs") and src.svc("wfs_typename"):
        return "wfs"
    if src.endpoint("wcs") and src.svc("wcs_coverage_id"):
        return "wcs"
    raise NotConfigured(
        f"[{src.id}] niente da scaricare: serve una di queste configurazioni in sources.toml\n"
        f"  - url: endpoints.download (link diretto al file)\n"
        f"  - wfs: endpoints.wfs + service.wfs_typename\n"
        f"  - wcs: endpoints.wcs + service.wcs_coverage_id, wcs_axis_x, wcs_axis_y, wcs_format\n"
        f"Valori [da verificare]: usa `python -m fiuto_pipeline capabilities {src.id}`.\n"
        f"In alternativa scarica a mano e imposta local_path."
    )


# --- url ------------------------------------------------------------------------


def _safe_extract(zpath: Path, dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    out = []
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            target = (dest / info.filename).resolve()
            if not target.is_relative_to(root):
                raise FiutoError(
                    f"{zpath}: percorso sospetto nello zip ({info.filename}), estrazione fermata"
                )
            if info.is_dir():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src_f, open(target, "wb") as dst_f:
                while chunk := src_f.read(1 << 20):
                    dst_f.write(chunk)
            out.append(target)
    return out


def fetch_url(src: Source, *, force: bool = False, log=print) -> Path | None:
    url = src.endpoint("download")
    if not url:
        raise NotConfigured(
            f"[{src.id}] endpoints.download vuoto [da verificare]: niente link diretto al file"
        )
    man = src.manifest() or {}
    cached = Path(man["download"]) if man.get("url") == url and man.get("download") else None
    if cached and cached.exists() and cached.stat().st_size > 0 and not force:
        dest = cached
        log(f"già in cache: {dest} (usa --force per riscaricare)")
    else:
        resp = get(session(), url, stream=True)
        dest = src.cache_dir / filename_from(resp, f"{src.id}.bin")
        log(f"scarico {url} -> {dest}")
        save_stream(resp, dest)
        if looks_like_xml(dest) and dest.suffix.lower() not in GEODATA_EXT:
            log(f"attenzione: {dest} sembra XML/HTML, non un dato (pagina di portale o errore?)")
    files = [dest]
    if zipfile.is_zipfile(dest):
        xdir = dest.parent / f"{dest.stem}_estratto"
        files = _safe_extract(dest, xdir)
        log(f"estratto in {xdir}")
    geo = [f for f in files if f.suffix.lower() in GEODATA_EXT]
    for f in geo:
        log(f"  dato: {f}")
    chosen = geo[0] if len(geo) == 1 else None
    if chosen is None:
        log(
            f"Più file (o nessuno riconosciuto): scegli quello giusto e scrivilo in "
            f"[sources.{src.id}] local_path."
        )
    write_manifest(src, chosen, method="url", url=url, download=str(dest), files=[str(f) for f in geo])
    return chosen


# --- wfs ------------------------------------------------------------------------


def fetch_wfs(
    src: Source,
    bbox: tuple[float, float, float, float],
    *,
    force: bool = False,
    page_size: int | None = None,
    log=print,
) -> Path:
    """GetFeature a pagine (STARTINDEX/COUNT) sul bbox, nel CRS della sorgente."""
    import geopandas as gpd
    import pandas as pd
    import pyogrio

    base = src.endpoint("wfs")
    if not base:
        raise NotConfigured(f"[{src.id}] endpoints.wfs vuoto [da verificare]")
    src.require("service", "wfs_typename", what="lo scarico WFS")
    if not src.crs:
        raise ConfigError(f"[{src.id}] manca crs in sources.toml")
    typename = src.svc("wfs_typename")
    version = str(src.svc("wfs_version", "2.0.0"))
    fmt = src.svc("wfs_output_format")
    count = int(page_size or src.svc("wfs_page_size", 1000))
    ext = ".json" if fmt and "json" in fmt.lower() else ".gml"
    # cache per richiesta: cambia bbox o parametri -> pagine nuove
    key = hashlib.sha1(json.dumps([typename, version, fmt, count, list(bbox), src.crs]).encode()).hexdigest()[
        :10
    ]
    pdir = src.cache_dir / "wfs" / f"{ows.local(typename)}_{key}"
    pdir.mkdir(parents=True, exist_ok=True)

    sess = session()
    pages: list[Path] = []
    start = 0
    while True:
        page = pdir / f"page_{start:08d}{ext}"
        if page.exists() and page.stat().st_size > 0 and not force:
            data = page.read_bytes()
        else:
            params = ows.wfs_getfeature_params(
                typename, version=version, start=start, count=count, bbox=bbox, crs=src.crs, output_format=fmt
            )
            log(f"GetFeature {typename} da {start}: {ows.build_url(base, params)}")
            data = get(sess, base, params=params).content
            if ext == ".gml":
                root_tag = data[:600].decode("utf-8", "replace")
                if "ExceptionReport" in root_tag:
                    raise FiutoError(f"[{src.id}] WFS: {ows.exception_message(ows.parse_xml(data))}")
            page.write_bytes(data)
        n = ows.number_returned(data) if ext == ".gml" else len(json.loads(data).get("features", []))
        if n is None:
            n = len(pyogrio.read_dataframe(page)) if page.stat().st_size else 0
        if n == 0:
            page.unlink(missing_ok=True)
            break
        pages.append(page)
        if n < count:
            break
        start += count

    if not pages:
        raise FiutoError(f"[{src.id}] WFS: nessuna feature nel bbox richiesto")
    frames = [pyogrio.read_dataframe(p) for p in pages]
    gdf = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)
    if gdf.crs is None:
        gdf = gdf.set_crs(src.crs)
    out = src.cache_dir / f"{src.id}_{ows.local(typename)}.gpkg"
    gdf.to_file(out, driver="GPKG", layer=ows.local(typename))
    log(f"{len(gdf)} feature in {len(pages)} pagine -> {out}")
    write_manifest(src, out, method="wfs", typename=typename, bbox=list(bbox), crs=src.crs, pages=len(pages))
    return out


# --- wcs ------------------------------------------------------------------------


def _ext_for(fmt: str) -> str:
    f = fmt.lower()
    if "tif" in f:
        return ".tif"
    if "asc" in f or "aaigrid" in f:
        return ".asc"
    raise ConfigError(f"formato WCS '{fmt}' non gestito: scegli un GeoTIFF dall'elenco di capabilities")


def _check_values_raster(path: Path, sid: str) -> None:
    """Un WCS può servire un'immagine colorata (RGB/RGBA) invece dei valori: in quel caso ci si ferma."""
    import rasterio

    with rasterio.open(path) as ds:
        count, dtype = ds.count, ds.dtypes[0]
    if count > 1:
        path.unlink()
        raise FiutoError(
            f"[{sid}] il WCS ha restituito {count} bande {dtype}: è un'immagine (es. RGBA), non un dato "
            f"di valori. Cerca un'altra coverage o il download del dato."
        )


def fetch_wcs(
    src: Source,
    bbox: tuple[float, float, float, float],
    *,
    force: bool = False,
    tile_size: float | None = None,
    align: float | None = None,
    log=print,
) -> Path:
    """GetCoverage a riquadri (WCS 2.0.1 o 1.0.0); ritorna la cartella dei tile (il build li legge tutti)."""
    base = src.endpoint("wcs")
    if not base:
        raise NotConfigured(f"[{src.id}] endpoints.wcs vuoto [da verificare]")
    src.require("service", "wcs_version", "wcs_coverage_id", "wcs_format", what="lo scarico WCS")
    version = str(src.svc("wcs_version"))
    if version == "2.0.1":
        src.require("service", "wcs_axis_x", "wcs_axis_y", what="lo scarico WCS 2.0.1")
    elif version == "1.0.0":
        src.require("service", "wcs_res", what="lo scarico WCS 1.0.0")
        if not src.crs:
            raise ConfigError(f"[{src.id}] manca crs (CRS nativo della coverage) in sources.toml")
    else:
        raise ConfigError(f"[{src.id}] service.wcs_version '{version}' non gestito (ammessi: 2.0.1, 1.0.0)")
    cid = src.svc("wcs_coverage_id")
    ext = _ext_for(src.svc("wcs_format"))
    size = float(tile_size or src.svc("wcs_tile_size_m", 5000))
    tdir = src.cache_dir / "wcs" / ows.local(cid)
    tdir.mkdir(parents=True, exist_ok=True)
    sess = session()
    tiles = ows.split_bbox(bbox, size, align)
    for i, tb in enumerate(tiles, start=1):
        dest = tdir / ("tile_" + "_".join(f"{v:.0f}" for v in tb) + ext)
        if dest.exists() and dest.stat().st_size > 0 and not force:
            continue
        if version == "2.0.1":
            params = ows.wcs_getcoverage_params(
                cid,
                axis_x=src.svc("wcs_axis_x"),
                axis_y=src.svc("wcs_axis_y"),
                bbox=tb,
                fmt=src.svc("wcs_format"),
            )
        else:
            params = ows.wcs100_getcoverage_params(
                cid, crs=src.crs, bbox=tb, res=float(src.svc("wcs_res")), fmt=src.svc("wcs_format")
            )
        log(f"[{i}/{len(tiles)}] GetCoverage {ows.build_url(base, params)}")
        resp = get(sess, base, params=params, stream=True)
        save_stream(resp, dest)
        if looks_like_xml(dest):
            body = dest.read_bytes()
            dest.unlink()
            try:
                msg = ows.exception_message(ows.parse_xml(body)) or body[:300].decode("utf-8", "replace")
            except ValueError:
                msg = body[:300].decode("utf-8", "replace")
            raise FiutoError(f"[{src.id}] WCS ha risposto con XML invece del raster: {msg}")
        _check_values_raster(dest, src.id)
    log(f"{len(tiles)} riquadri in {tdir}")
    write_manifest(src, tdir, method="wcs", coverage=cid, bbox=list(bbox), crs=src.crs, tiles=len(tiles))
    return tdir


def run_fetch(
    src: Source,
    *,
    method: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    force: bool = False,
    align: float | None = None,
    log=print,
) -> Path | None:
    m = choose_method(src, method)
    if m == "url":
        return fetch_url(src, force=force, log=log)
    if bbox is None:
        raise ConfigError(f"lo scarico {m.upper()} lavora su un'area: passa --aoi <nome> (vedi aoi.toml)")
    if m == "wfs":
        return fetch_wfs(src, bbox, force=force, log=log)
    return fetch_wcs(src, bbox, force=force, align=align, log=log)


# --- ArcGIS REST (MapServer/FeatureServer query) ----------------------------------------


def arcgis_query_params(
    bbox: tuple[float, float, float, float], *, in_epsg: int, fields: list[str], start: int, count: int
) -> list[tuple[str, str]]:
    """Parametri di /query: envelope nel CRS dato, risultato GeoJSON in EPSG:4326, pagine ordinate."""
    minx, miny, maxx, maxy = bbox
    return [
        ("where", "1=1"),
        ("geometry", f"{minx!r},{miny!r},{maxx!r},{maxy!r}"),
        ("geometryType", "esriGeometryEnvelope"),
        ("inSR", str(in_epsg)),
        ("spatialRel", "esriSpatialRelIntersects"),
        ("outFields", ",".join(fields) if fields else "OBJECTID"),
        ("returnGeometry", "true"),
        ("outSR", "4326"),
        ("orderByFields", "OBJECTID"),
        ("resultOffset", str(start)),
        ("resultRecordCount", str(count)),
        ("f", "geojson"),
    ]


def fetch_arcgis_layer(
    src: Source,
    layer: int | str,
    bbox: tuple[float, float, float, float],
    *,
    fields: list[str],
    force: bool = False,
    page_size: int = 1000,
    log=print,
):
    """Interroga un layer di un MapServer ArcGIS (endpoints.rest) a pagine; GeoDataFrame in EPSG:4326.

    Le pagine restano in cache in data/raw/<sorgente>/rest/. `bbox` è nel CRS della sorgente.
    """
    import geopandas as gpd
    from pyproj import CRS

    base = src.endpoint("rest")
    if not base:
        raise NotConfigured(f"[{src.id}] endpoints.rest vuoto [da verificare]")
    if not src.crs:
        raise ConfigError(f"[{src.id}] manca crs in sources.toml")
    epsg = CRS.from_user_input(src.crs).to_epsg()
    url = f"{base.rstrip('/')}/{layer}/query"
    key = hashlib.sha1(json.dumps([url, list(bbox), sorted(fields), page_size]).encode()).hexdigest()[:10]
    pdir = src.cache_dir / "rest" / f"{layer}_{key}"
    pdir.mkdir(parents=True, exist_ok=True)
    sess = session()
    feats: list[dict] = []
    start = 0
    while True:
        page = pdir / f"page_{start:08d}.json"
        if page.exists() and page.stat().st_size > 0 and not force:
            data = json.loads(page.read_text(encoding="utf-8"))
        else:
            params = arcgis_query_params(bbox, in_epsg=epsg, fields=fields, start=start, count=page_size)
            log(f"[{src.id}] query layer {layer} da {start}")
            resp = get(sess, url, params=params)
            try:
                data = resp.json()
            except ValueError as exc:
                raise FiutoError(f"[{src.id}] risposta non JSON da {url}") from exc
            if "error" in data:
                raise FiutoError(f"[{src.id}] errore ArcGIS da {url}: {data['error']}")
            page.write_text(json.dumps(data), encoding="utf-8")
        got = data.get("features", [])
        feats += got
        if len(got) < page_size:
            break
        start += page_size
    gdf = gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326") if feats else gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    return gdf
