"""Lettura dati locali (raster e vettori) e passaggio sulla griglia comune."""

from __future__ import annotations

import math
import warnings
from pathlib import Path

import numpy as np
import pyogrio
import rasterio
from pyproj import CRS
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import Window

from .errors import ConfigError
from .grid import Grid
from .lookups import norm_key

RASTER_EXT = {".tif", ".tiff", ".asc", ".img", ".vrt", ".bil", ".flt"}


def is_raster(path: Path) -> bool:
    """True se il percorso è un raster (o una cartella di raster)."""
    if path.is_dir():
        return any(p.suffix.lower() in RASTER_EXT for p in path.iterdir())
    if path.suffix.lower() in RASTER_EXT:
        return True
    try:
        with rasterio.open(path):
            return True
    except Exception:
        return False


def raster_files(path: Path) -> list[Path]:
    """Un file raster, oppure tutti i raster di una cartella (es. tile WCS)."""
    if path.is_dir():
        files = sorted(p for p in path.iterdir() if p.suffix.lower() in RASTER_EXT)
        if not files:
            raise ConfigError(f"nessun raster in {path}")
        return files
    return [path]


def resample_to_grid(
    path: Path,
    grid: Grid,
    *,
    resampling: Resampling = Resampling.average,
    band: int = 1,
    default_crs: str = "",
    scale: float = 1.0,
    nodata: float | None = None,
) -> np.ndarray:
    """Porta uno o più raster sulla griglia (float32, NaN = assente).

    Più file (es. tile) vengono scritti uno alla volta nella finestra che
    coprono; dove si sovrappongono vince il primo. `nodata` si usa solo se il
    file non lo dichiara (es. tile WCS senza nodata nel GeoTIFF).
    """
    out = np.full(grid.shape, np.nan, dtype="float32")
    for f in raster_files(path):
        with rasterio.open(f) as src:
            src_crs = src.crs
            if src_crs is None:
                if not default_crs:
                    raise ConfigError(f"{f}: il raster non dichiara il CRS e in sources.toml manca crs")
                warnings.warn(f"{f}: CRS assente, uso {default_crs} da sources.toml", stacklevel=2)
                src_crs = CRS.from_user_input(default_crs)
            if band < 1 or band > src.count:
                raise ConfigError(f"{f}: banda {band} inesistente (il raster ne ha {src.count})")
            # finestra della griglia coperta dal file (arrotondata verso l'esterno)
            bx0, by0, bx1, by1 = transform_bounds(src_crs, grid.crs, *src.bounds, densify_pts=21)
            gx0, gy1, cs = grid.transform.c, grid.transform.f, grid.cell_size
            col0 = max(math.floor((bx0 - gx0) / cs), 0)
            col1 = min(math.ceil((bx1 - gx0) / cs), grid.width)
            row0 = max(math.floor((gy1 - by1) / cs), 0)
            row1 = min(math.ceil((gy1 - by0) / cs), grid.height)
            if col1 <= col0 or row1 <= row0:
                continue  # il file non tocca la griglia
            w = Window(col0, row0, col1 - col0, row1 - row0)
            dst = np.full((int(w.height), int(w.width)), np.nan, dtype="float32")
            reproject(
                source=rasterio.band(src, band),
                destination=dst,
                src_crs=src_crs,
                src_nodata=src.nodata if src.nodata is not None else nodata,
                dst_transform=rasterio.windows.transform(w, grid.transform),
                dst_crs=grid.crs,
                dst_nodata=np.nan,
                resampling=resampling,
            )
            sub = out[row0:row1, col0:col1]
            fill = np.isnan(sub) & ~np.isnan(dst)
            sub[fill] = dst[fill]
    if scale != 1.0:
        out *= np.float32(scale)
    return out


def check_range(
    values: np.ndarray, lo: float, hi: float, what: str, max_bad_share: float = 0.005
) -> np.ndarray:
    """Valori fuori da un intervallo fisicamente plausibile.

    Pochi valori strani -> NaN con avviso. Tanti -> errore: di solito è un
    nodata non dichiarato o una scala sbagliata, meglio fermarsi.
    """
    valid = np.isfinite(values)
    n_valid = int(valid.sum())
    if n_valid == 0:
        return values
    bad = valid & ((values < lo) | (values > hi))
    n_bad = int(bad.sum())
    if n_bad == 0:
        return values
    vmin, vmax = float(np.nanmin(values)), float(np.nanmax(values))
    if n_bad / n_valid > max_bad_share:
        raise ConfigError(
            f"{what}: {n_bad} celle su {n_valid} fuori da {lo:g}..{hi:g} (min {vmin:g}, max {vmax:g}). "
            f"Verifica nodata e scala del dato (es. pH in decimi) in sources.toml prima di continuare."
        )
    warnings.warn(f"{what}: {n_bad} celle fuori da {lo:g}..{hi:g} trattate come assenti", stacklevel=2)
    out = values.copy()
    out[bad] = np.nan
    return out


# --- vettori ---------------------------------------------------------------


def pick_layer(path: Path, layer: str | None, sid: str) -> str | None:
    layers = [str(row[0]) for row in pyogrio.list_layers(path)]
    if layer:
        if layer not in layers:
            raise ConfigError(
                f"[{sid}] layer '{layer}' non trovato in {path}. Layer presenti: {', '.join(layers)}"
            )
        return layer
    if len(layers) == 1:
        return layers[0]
    raise ConfigError(
        f"[{sid}] {path} contiene più layer ({', '.join(layers)}): "
        f"scegli quello giusto in sources.toml (attributes.layer)."
    )


def read_vector(
    path: Path,
    grid: Grid,
    *,
    sid: str,
    layer: str | None,
    columns: list[str],
    default_crs: str = "",
    where: str | None = None,
):
    """Legge un vettore limitato al bbox della griglia e lo porta nel CRS di lavoro.

    Se un attributo richiesto non esiste, errore con l'elenco di quelli presenti.
    """
    import geopandas as gpd

    lyr = pick_layer(path, layer, sid)
    info = pyogrio.read_info(path, layer=lyr)
    fields = [str(f) for f in info["fields"]]
    missing = [c for c in columns if c not in fields]
    if missing:
        raise ConfigError(
            f"[{sid}] attributi {missing} non trovati nel layer '{lyr}' di {path}. "
            f"Attributi presenti: {', '.join(fields)}"
        )
    src_crs = info.get("crs")
    if not src_crs:
        if not default_crs:
            raise ConfigError(f"[{sid}] {path} non dichiara il CRS e in sources.toml manca crs")
        warnings.warn(f"[{sid}] {path}: CRS assente, uso {default_crs} da sources.toml", stacklevel=2)
        src_crs = default_crs
    bbox = grid.bounds_in(src_crs)
    # Con un filtro `where` si leggono tutti i campi: con alcuni driver (es. Shapefile) GDAL ignora
    # i campi non selezionati prima di filtrare e il filtro non trova più niente.
    gdf = pyogrio.read_dataframe(
        path, layer=lyr, columns=None if where else columns, bbox=bbox, where=where or None
    )
    if where:
        gdf = gdf[[c for c in columns if c in gdf.columns] + [gdf.geometry.name]]
    if gdf.crs is None:
        gdf = gdf.set_crs(src_crs)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
    if CRS.from_user_input(gdf.crs) != CRS.from_user_input(grid.crs):
        gdf = gdf.to_crs(grid.crs)
    return gpd.GeoDataFrame(gdf, crs=grid.crs)


def rasterize_values(gdf, column: str, grid: Grid) -> np.ndarray:
    """Attributo numerico -> griglia float32 (NaN dove non ci sono poligoni o il valore manca).

    Un attributo testuale non viene convertito a forza (es. "7,2" o "6.5-7"):
    errore, perché va capito com'è fatto il dato.
    """
    import pandas as pd

    raw = gdf[column]
    vals = pd.to_numeric(raw, errors="coerce").astype("float64")
    bad = raw.notna() & vals.isna()
    if bad.any():
        examples = ", ".join(repr(v) for v in raw[bad].astype(str).unique()[:5])
        raise ConfigError(
            f"attributo '{column}' non numerico in {int(bad.sum())} poligoni (es. {examples}). "
            f"Verifica il formato del dato: virgola decimale, classi invece di valori?"
        )
    shapes = [(g, float(v)) for g, v in zip(gdf.geometry, vals) if v == v]
    if not shapes:
        return np.full(grid.shape, np.nan, dtype="float32")
    return rasterize(shapes, out_shape=grid.shape, transform=grid.transform, fill=np.nan, dtype="float32")


def rasterize_codes(gdf, column: str, grid: Grid) -> tuple[np.ndarray, list[str]]:
    """Attributo categorico -> (indici int32 sulla griglia, -1 = assente; elenco valori)."""
    labels: dict[str, int] = {}
    shapes = []
    for g, v in zip(gdf.geometry, gdf[column]):
        k = norm_key(v)
        if k is None:
            continue
        idx = labels.setdefault(k, len(labels))
        shapes.append((g, idx))
    if not shapes:
        return np.full(grid.shape, -1, dtype="int32"), []
    codes = rasterize(shapes, out_shape=grid.shape, transform=grid.transform, fill=-1, dtype="int32")
    return codes, list(labels)


def rasterize_mask(gdf, grid: Grid) -> np.ndarray:
    """Qualsiasi poligono -> True."""
    if gdf.empty:
        return np.zeros(grid.shape, dtype=bool)
    return rasterize(
        ((g, 1) for g in gdf.geometry), out_shape=grid.shape, transform=grid.transform, fill=0, dtype="uint8"
    ).astype(bool)


def rasterize_index(gdf, grid: Grid) -> np.ndarray:
    """Posizione (0..n-1) del poligono in ogni cella, -1 dove non c'è niente."""
    if gdf.empty:
        return np.full(grid.shape, -1, dtype="int32")
    shapes = ((g, i) for i, g in enumerate(gdf.geometry))
    return rasterize(shapes, out_shape=grid.shape, transform=grid.transform, fill=-1, dtype="int32")


def codes_from_index(index: np.ndarray, values) -> tuple[np.ndarray, list[str]]:
    """Come `rasterize_codes`, ma partendo dall'indice dei poligoni (un solo rasterize per più attributi)."""
    labels: dict[str, int] = {}
    per_poly = np.full(len(values) + 1, -1, dtype="int32")  # ultimo = indice -1
    for i, v in enumerate(values):
        k = norm_key(v)
        if k is not None:
            per_poly[i] = labels.setdefault(k, len(labels))
    return per_poly[index], list(labels)
