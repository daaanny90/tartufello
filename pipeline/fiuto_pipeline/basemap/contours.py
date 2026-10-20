"""Curve di livello dal DTM (già ricampionato a ~10 m).

Leggera lisciatura (filtro binomiale 5x5, che tiene conto dei nodata), curve
con contourpy, semplificazione e scarto dei frammenti troppo corti.
"""

from __future__ import annotations

import math

import numpy as np

_KERNEL = np.array([1.0, 4.0, 6.0, 4.0, 1.0]) / 16.0


def smooth(z: np.ndarray, passes: int = 1) -> np.ndarray:
    """Media binomiale separabile; i nodata restano nodata e non sporcano i vicini."""
    z = np.asarray(z, dtype="float64")
    valid = np.isfinite(z)
    out = np.where(valid, z, 0.0)
    w = valid.astype("float64")
    for _ in range(passes):
        for axis in (0, 1):
            out = _conv1d(out, axis)
            w = _conv1d(w, axis)
        with np.errstate(invalid="ignore", divide="ignore"):
            out = np.where(w > 0, out / w, 0.0)
        w = valid.astype("float64")
        out = np.where(valid, out, 0.0)
    return np.where(valid, out, np.nan)


def _conv1d(a: np.ndarray, axis: int) -> np.ndarray:
    pad = [(0, 0), (0, 0)]
    pad[axis] = (2, 2)
    p = np.pad(a, pad, mode="constant")
    n = a.shape[axis]
    acc = np.zeros_like(a)
    for k, wk in enumerate(_KERNEL):
        sl = [slice(None), slice(None)]
        sl[axis] = slice(k, k + n)
        acc += wk * p[tuple(sl)]
    return acc


def contour_lines(
    z: np.ndarray,
    transform,
    *,
    interval: float = 10.0,
    major_every: float = 50.0,
    min_length: float = 100.0,
    simplify: float = 2.0,
) -> list[tuple[int, bool, object]]:
    """Ritorna [(quota, maggiore, LineString), ...] nel CRS del `transform` (metri).

    Le curve più corte di `min_length` metri (anelli e pezzetti) vengono scartate.
    """
    from contourpy import LineType, contour_generator
    from shapely.geometry import LineString

    h, w = z.shape
    # centri cella; righe dal basso verso l'alto per avere y crescente
    xs = transform.c + (np.arange(w) + 0.5) * transform.a
    ys = transform.f + (np.arange(h) + 0.5) * transform.e
    zz = np.ma.masked_invalid(z[::-1, :])
    ys = ys[::-1]
    if zz.count() == 0:
        return []
    gen = contour_generator(x=xs, y=ys, z=zz, line_type=LineType.Separate)
    lo = math.ceil(float(zz.min()) / interval) * interval
    hi = math.floor(float(zz.max()) / interval) * interval
    out = []
    level = lo
    while level <= hi + 1e-9:
        ele = int(round(level))
        major = ele % int(round(major_every)) == 0
        for coords in gen.lines(level):
            if len(coords) < 2:
                continue
            line = LineString(coords)
            if line.length < min_length:
                continue
            if simplify:
                line = line.simplify(simplify, preserve_topology=False)
            if line.length >= min_length and len(line.coords) >= 2:
                out.append((ele, major, line))
        level += interval
    return out
