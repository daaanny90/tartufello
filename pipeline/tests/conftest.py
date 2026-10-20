"""Fixture comuni. TUTTI i dati qui sono SINTETICI, costruiti nei test.

Nessun codice, attributo o valore regionale reale: nomi come "sint_code" o
"U_SINT_1" sono inventati apposta e valgono solo per i test.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import numpy as np
import pytest
import rasterio
from affine import Affine

from fiuto_pipeline.grid import Grid
from fiuto_pipeline.model import DEFAULT_MODEL_PATH, MODEL_V1_PATH, load_model

# Area sintetica in EPSG:5659 (metri), 2 km x 1 km
X0, Y0 = 600_000.0, 930_000.0
W_M, H_M = 2_000.0, 1_000.0


@pytest.fixture(scope="session")
def model():
    """Modello corrente (vth-v2)."""
    return load_model()


@pytest.fixture(scope="session")
def model_v1():
    """vth-v1 resta leggibile: alcuni test lo usano apposta (es. ospiti da remoto)."""
    return load_model(MODEL_V1_PATH)


@pytest.fixture
def grid():
    return Grid.from_bounds((X0, Y0, X0 + W_M, Y0 + H_M), "EPSG:5659", 25.0)


def write_raster(
    path: Path, data: np.ndarray, *, x0: float, y1: float, res: float, crs: str, nodata=None
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=data.shape[1],
        height=data.shape[0],
        count=1,
        dtype=data.dtype,
        crs=crs,
        transform=Affine(res, 0, x0, 0, -res, y1),
        nodata=nodata,
    ) as dst:
        dst.write(data, 1)
    return path


def write_vector(
    path: Path, records: list[dict], geoms: list, crs: str = "EPSG:5659", layer: str | None = None
) -> Path:
    import geopandas as gpd

    path.parent.mkdir(parents=True, exist_ok=True)
    gdf = gpd.GeoDataFrame(records, geometry=geoms, crs=crs)
    if path.suffix.lower() == ".shp":
        gdf.to_file(path, driver="ESRI Shapefile")
    else:
        gdf.to_file(path, driver="GPKG", layer=layer or path.stem)
    return path


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")
    return path


@pytest.fixture
def model_path():
    return DEFAULT_MODEL_PATH
