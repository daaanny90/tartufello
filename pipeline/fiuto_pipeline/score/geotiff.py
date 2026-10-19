"""GeoTIFF multibanda dello score (EPSG:5659), per controlli in QGIS.

Tutte le bande uint16, nodata 65535 (GeoTIFF ha un solo nodata per file):
  1 score_x1000  score 0..1 moltiplicato per 1000 (arrotondato)
  2 pts, 3 max, 4 n   (nodata fuori maschera)
  5 mask         1 = cella considerata (bosco e AOI), 0 = no
  6.. un parametro per banda, nell'ordine del modello (nodata = non disponibile)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio

from ..grid import Grid
from ..model import NA, Model
from .combine import ScoreResult

NODATA = 65535


def band_names(model: Model) -> list[str]:
    return ["score_x1000", "pts", "max", "n", "mask"] + model.remote_params()


def write_score_geotiff(
    path: Path,
    grid: Grid,
    result: ScoreResult,
    params: dict[str, np.ndarray],
    model: Model,
    tags: dict | None = None,
) -> Path:
    names = band_names(model)
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = dict(
        driver="GTiff",
        width=grid.width,
        height=grid.height,
        count=len(names),
        dtype="uint16",
        crs=grid.crs,
        transform=grid.transform,
        nodata=NODATA,
        compress="deflate",
        predictor=2,
        tiled=True,
        blockxsize=256,
        blockysize=256,
    )
    with rasterio.open(path, "w", **profile) as dst:
        score = np.full(grid.shape, NODATA, dtype="uint16")
        ok = result.has_score
        score[ok] = result.score_milli()[ok].astype("uint16")
        bands = [score]
        for arr in (result.pts, result.max, result.n):
            b = arr.astype("uint16")
            b[~result.mask] = NODATA
            bands.append(b)
        bands.append(result.mask.astype("uint16"))
        for pid in model.remote_params():
            arr = params.get(pid)
            b = np.full(grid.shape, NODATA, dtype="uint16")
            if arr is not None:
                avail = arr != NA
                b[avail] = arr[avail]
            bands.append(b)
        for i, (name, b) in enumerate(zip(names, bands), start=1):
            dst.write(b, i)
            dst.set_band_description(i, name)
        dst.update_tags(**{k: str(v) for k, v in (tags or {}).items()})
    return path
