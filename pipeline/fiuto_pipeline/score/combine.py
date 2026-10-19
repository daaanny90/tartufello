"""Score remoto VTH normalizzato (BRIEF §4.3, model.remote).

pts = somma dei punti dei parametri disponibili nella cella
max = somma dei massimi remoti (dal modello) degli stessi parametri
n   = numero di parametri disponibili
score = pts / max, solo se n >= minParams e la cella è nella maschera bosco.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..errors import ModelError
from ..model import NA, Model


def score_milli(pts: np.ndarray, mx: np.ndarray) -> np.ndarray:
    """Score in millesimi, arrotondato a metà per eccesso (0.3125 -> 313).

    Calcolato in float64 dagli interi pts/max: stesso risultato in GeoTIFF,
    tile e app (Math.round fa lo stesso), niente arrotondamento al pari.
    """
    pts = np.asarray(pts, dtype="float64")
    mx = np.asarray(mx, dtype="float64")
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.floor(pts * 1000.0 / mx + 0.5)


@dataclass
class ScoreResult:
    score: np.ndarray  # float32, NaN dove non calcolato
    pts: np.ndarray  # uint16
    max: np.ndarray  # uint16
    n: np.ndarray  # uint8
    mask: np.ndarray  # bool, celle considerate (bosco e AOI)

    @property
    def has_score(self) -> np.ndarray:
        return np.isfinite(self.score)

    def score_milli(self) -> np.ndarray:
        """Score x1000 arrotondato (float64, NaN dove non calcolato)."""
        out = score_milli(self.pts, self.max)
        out[~self.has_score] = np.nan
        return out


def combine(params: dict[str, np.ndarray], model: Model, mask: np.ndarray | None = None) -> ScoreResult:
    """Combina gli array di punti (uint8, 255 = NA). I parametri assenti valgono NA."""
    remote = model.remote_params()
    unknown = set(params) - set(remote)
    if unknown:
        raise ModelError(f"parametri non remoti o sconosciuti: {sorted(unknown)} (remoti: {remote})")
    shape = next(iter(params.values())).shape if params else (mask.shape if mask is not None else None)
    if shape is None:
        raise ValueError("servono almeno un parametro o una maschera")
    if mask is None:
        mask = np.ones(shape, dtype=bool)

    pts = np.zeros(shape, dtype="uint16")
    mx = np.zeros(shape, dtype="uint16")
    n = np.zeros(shape, dtype="uint8")
    for pid in remote:
        arr = params.get(pid)
        if arr is None:
            continue
        if arr.shape != shape:
            raise ValueError(f"{pid}: forma {arr.shape} diversa da {shape}")
        avail = arr != NA
        pmax = model.remote_max(pid)
        if np.any(arr[avail] > pmax):
            raise ModelError(f"{pid}: punti oltre il massimo remoto del modello ({pmax})")
        pts += np.where(avail, arr, 0).astype("uint16")
        mx += avail.astype("uint16") * pmax
        n += avail.astype("uint8")

    ok = mask & (n >= model.min_params) & (mx > 0)
    score = np.full(shape, np.nan, dtype="float32")
    score[ok] = pts[ok].astype("float32") / mx[ok].astype("float32")
    # fuori maschera nessun conteggio
    pts[~mask] = 0
    mx[~mask] = 0
    n[~mask] = 0
    return ScoreResult(score=score, pts=pts, max=mx, n=n, mask=mask)
