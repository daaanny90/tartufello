"""Rilievo ombreggiato dal DTM e PMTiles raster per la mappa offline.

Ombreggiatura classica (Horn, sole a 315° e 45° di altezza), in scala di
grigi, nodata trasparente. I tile si scrivono con il driver MBTiles di GDAL
(rasterio) e si convertono in PMTiles con il pacchetto `pmtiles`: il driver
PMTiles di GDAL non scrive raster.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import numpy as np

# Risoluzione di un pixel EPSG:3857 a zoom 0 con tile da 256 px
WEB_MERCATOR_RES0 = 2 * math.pi * 6378137 / 256


def hillshade(
    z: np.ndarray, cellsize: float, *, azimuth: float = 315.0, altitude: float = 45.0, z_factor: float = 1.0
) -> tuple[np.ndarray, np.ndarray]:
    """Ombreggiatura di Horn. Ritorna (grigio uint8, valido bool).

    Una cella senza tutti gli 8 vicini validi (bordi, nodata) non è valida.
    Pendenza nulla = 255 * cos(90° - altitude) (180 con sole a 45°).
    """
    z = np.asarray(z, dtype="float64")
    p = np.pad(z, 1, mode="constant", constant_values=np.nan)
    a, b, c = p[:-2, :-2], p[:-2, 1:-1], p[:-2, 2:]
    d, f = p[1:-1, :-2], p[1:-1, 2:]
    g, h, i = p[2:, :-2], p[2:, 1:-1], p[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8.0 * cellsize)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8.0 * cellsize)
    valid = np.isfinite(dzdx) & np.isfinite(dzdy) & np.isfinite(z)
    dzdx = np.where(valid, dzdx, 0.0)
    dzdy = np.where(valid, dzdy, 0.0)
    zenith = math.radians(90.0 - altitude)
    az = math.radians((360.0 - azimuth + 90.0) % 360.0)
    slope = np.arctan(z_factor * np.hypot(dzdx, dzdy))
    aspect = np.arctan2(dzdy, -dzdx)
    shade = math.cos(zenith) * np.cos(slope) + math.sin(zenith) * np.sin(slope) * np.cos(az - aspect)
    gray = np.clip(np.rint(255.0 * shade), 0, 255).astype("uint8")
    gray[~valid] = 0
    return gray, valid


def zoom_resolution(zoom: int) -> float:
    return WEB_MERCATOR_RES0 / (2**zoom)


def write_hillshade_pmtiles(
    gray: np.ndarray,
    valid: np.ndarray,
    transform,
    crs: str,
    out: Path,
    *,
    minzoom: int,
    maxzoom: int,
    metadata: dict,
    tile_format: str | None = None,
    quality: int = 80,
) -> dict:
    """Riproietta in EPSG:3857 alla risoluzione di maxzoom, scrive MBTiles (+ overview) e converte in PMTiles."""
    import rasterio
    import rasterio.shutil
    from pmtiles.convert import mbtiles_to_pmtiles
    from rasterio.enums import Resampling
    from rasterio.env import Env
    from rasterio.warp import calculate_default_transform, reproject

    from ..export.tiles import set_pmtiles_metadata

    with Env() as env:
        drivers = env.drivers()
    fmt = tile_format or ("WEBP" if "WEBP" in drivers else "PNG")
    h, w = gray.shape
    res = zoom_resolution(maxzoom)
    left, top = transform.c, transform.f
    right, bottom = left + w * transform.a, top + h * transform.e
    dst_transform, dw, dh = calculate_default_transform(
        crs, "EPSG:3857", w, h, left=left, bottom=bottom, right=right, top=top, resolution=res
    )
    g3857 = np.zeros((dh, dw), dtype="uint8")
    a3857 = np.zeros((dh, dw), dtype="uint8")
    common = dict(src_transform=transform, src_crs=crs, dst_transform=dst_transform, dst_crs="EPSG:3857")
    reproject(gray, g3857, resampling=Resampling.bilinear, **common)
    reproject(valid.astype("uint8") * 255, a3857, resampling=Resampling.nearest, **common)
    g3857[a3857 == 0] = 0

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        tif = Path(td) / "rilievo_3857.tif"
        profile = dict(
            driver="GTiff",
            width=dw,
            height=dh,
            count=4,
            dtype="uint8",
            crs="EPSG:3857",
            transform=dst_transform,
        )
        with rasterio.open(tif, "w", **profile) as ds:
            for band in (1, 2, 3):  # grigio in RGB: WEBP/PNG con trasparenza
                ds.write(g3857, band)
            ds.write(a3857, 4)
        mb = Path(td) / "rilievo.mbtiles"
        opts = {"TILE_FORMAT": fmt, "ZOOM_LEVEL_STRATEGY": "AUTO", "NAME": metadata.get("name", "rilievo")}
        if fmt in ("WEBP", "JPEG"):
            opts["QUALITY"] = str(quality)
        rasterio.shutil.copy(tif, mb, driver="MBTiles", **opts)
        factors = [2**k for k in range(1, maxzoom - minzoom + 1)]
        with rasterio.open(mb, "r+") as ds:
            ds.build_overviews(factors, Resampling.average)
        if out.exists():
            out.unlink()
        mbtiles_to_pmtiles(str(mb), str(out), maxzoom)
    meta = set_pmtiles_metadata(
        out, {**metadata, "format": fmt.lower(), "minzoom": minzoom, "maxzoom": maxzoom}
    )
    from pmtiles.reader import MmapSource, Reader

    with open(out, "rb") as f:
        header = Reader(MmapSource(f)).header()
    res = {
        "path": str(out),
        "bytes": out.stat().st_size,
        "format": fmt,
        "min_zoom": header["min_zoom"],
        "max_zoom": header["max_zoom"],
        "tiles": header["addressed_tiles_count"],
        "metadata_keys": sorted(meta),
    }
    if header["min_zoom"] > minzoom:
        # GDAL non crea le overview più piccole di qualche decina di pixel: con un'AOI piccola
        # i primi zoom mancano (a quegli zoom l'area è comunque un francobollo)
        res["note"] = (
            f"zoom {minzoom}-{header['min_zoom'] - 1} non scritti: AOI troppo piccola per quelle overview"
        )
    return res
