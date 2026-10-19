"""Da griglie di punti a poligoni con le proprietà del contratto `tiles` del modello.

Ogni poligono è un'area connessa con la stessa combinazione di punti per
parametro. Le proprietà (pts, max, n, score) si ricalcolano dalla combinazione
con lo stesso codice dello score, quindi non possono divergere.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from rasterio.features import shapes
from shapely.geometry import shape

from ..errors import ModelError
from ..grid import Grid
from ..model import NA, Model
from ..score.combine import combine

BITS = 3  # 0..3 punti + 4 = non disponibile
NA_CODE = 4
BASE_KEYS = ("score", "pts", "max", "n")


def contract_keys(model: Model) -> list[str]:
    """Chiavi ammesse nelle feature, nell'ordine del contratto."""
    keys = list(model.tile_properties)
    for pid in model.remote_params():
        if pid not in keys:
            raise ModelError(f"il parametro remoto '{pid}' non è nel contratto tiles.properties")
    for k in BASE_KEYS:
        if k not in keys:
            raise ModelError(f"'{k}' manca nel contratto tiles.properties")
    return keys


def encode(params: dict[str, np.ndarray], model: Model, mask: np.ndarray) -> np.ndarray:
    """Chiave int32 per cella che codifica i punti di tutti i parametri; -1 fuori maschera."""
    order = model.remote_params()
    if BITS * len(order) > 30:
        raise ModelError("troppi parametri remoti per la chiave int32")
    key = np.zeros(mask.shape, dtype="int32")
    for i, pid in enumerate(order):
        arr = params.get(pid)
        if arr is None:
            code = np.full(mask.shape, NA_CODE, dtype="int32")
        else:
            if np.any((arr != NA) & (arr > 3)):
                raise ModelError(f"{pid}: punti oltre 3 non codificabili")
            code = np.where(arr == NA, NA_CODE, arr).astype("int32")
        key |= code << (BITS * i)
    key[~mask] = -1
    return key


def decode(keys: np.ndarray, model: Model) -> dict[str, np.ndarray]:
    """Inverso di `encode` (su chiavi >= 0): array uint8 per parametro, 255 = NA."""
    out = {}
    for i, pid in enumerate(model.remote_params()):
        code = (keys >> (BITS * i)) & 0b111
        out[pid] = np.where(code == NA_CODE, NA, code).astype("uint8")
    return out


def properties_table(keys: np.ndarray, model: Model) -> pd.DataFrame:
    """Proprietà del contratto per ogni chiave (colonne nullable: NA = chiave omessa)."""
    keys = np.asarray(keys, dtype="int32")
    params = decode(keys, model)
    res = combine(params, model, mask=np.ones(keys.shape, dtype=bool))
    df = pd.DataFrame(index=range(len(keys)))
    score = res.score_milli() / 1000.0
    col_score = pd.array(np.nan_to_num(score, nan=0.0), dtype="Float64")
    col_score[~np.isfinite(score)] = pd.NA
    df["score"] = col_score
    df["pts"] = res.pts.astype("int32")
    df["max"] = res.max.astype("int32")
    df["n"] = res.n.astype("int32")
    for pid in model.remote_params():
        arr = params[pid].astype("int32")
        col = pd.array(arr, dtype="Int32")
        col[params[pid] == NA] = pd.NA
        df[pid] = col
    return df[[k for k in contract_keys(model) if k in df.columns]]


def polygonize(params: dict[str, np.ndarray], mask: np.ndarray, grid: Grid, model: Model):
    """Poligoni (GeoDataFrame nel CRS della griglia) con le proprietà del contratto."""
    import geopandas as gpd

    key = encode(params, model, mask)
    geoms, keys = [], []
    for geom, value in shapes(key, mask=key >= 0, transform=grid.transform, connectivity=4):
        geoms.append(shape(geom))
        keys.append(int(value))
    if not geoms:
        props = properties_table(np.zeros(0, dtype="int32"), model)
        return gpd.GeoDataFrame(props, geometry=[], crs=grid.crs)
    props = properties_table(np.array(keys, dtype="int32"), model)
    return gpd.GeoDataFrame(props, geometry=geoms, crs=grid.crs)


def feature_properties(row: dict, keys: list[str]) -> dict:
    """Dizionario per una feature: chiavi con valore mancante omesse, interi come int."""
    out = {}
    for k in keys:
        v = row.get(k)
        if v is None or v is pd.NA or (isinstance(v, float) and v != v):
            continue
        out[k] = round(float(v), 3) if k == "score" else int(v)
    return out
