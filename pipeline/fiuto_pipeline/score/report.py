"""Report JSON del build e CSV dei valori ancora da classificare."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from ..lookups import SPECS
from ..model import NA, Model
from .combine import ScoreResult

# param -> (tabella di lookup, colonna del valore, colonna del nome)
UNMAPPED_TARGET = {
    "texture": ("suoli_tessitura", "valore_er", None),
    "bedrock": ("geologia_vth", "unit_code", "unit_name"),
    "forest_type": ("forestale_vth", "tipo_er", "tipo_er_nome"),
    "hosts": ("forestale_vth", "tipo_er", "tipo_er_nome"),
}


def availability(params: dict[str, np.ndarray], mask: np.ndarray, model: Model) -> dict[str, float]:
    """Quota (%) di celle nella maschera con il parametro disponibile."""
    total = int(mask.sum())
    out = {}
    for pid in model.remote_params():
        arr = params.get(pid)
        if arr is None or total == 0:
            out[pid] = 0.0
        else:
            out[pid] = round(100.0 * int(((arr != NA) & mask).sum()) / total, 2)
    return out


def score_stats(result: ScoreResult, model: Model, cell_ha: float) -> dict:
    ok = result.has_score
    cells_mask = int(result.mask.sum())
    vals = result.score[ok]
    stats = {
        "cells_mask": cells_mask,
        "ha_mask": round(cells_mask * cell_ha, 2),
        "cells_score": int(ok.sum()),
        "share_score_pct": round(100.0 * int(ok.sum()) / cells_mask, 2) if cells_mask else 0.0,
        "cells_insufficient": int((result.mask & ~ok).sum()),
        "min_params": model.min_params,
    }
    if vals.size:
        stats.update(
            score_min=round(float(vals.min()), 3),
            score_mean=round(float(vals.mean()), 3),
            score_max=round(float(vals.max()), 3),
            score_hist_deciles=np.histogram(vals, bins=10, range=(0.0, 1.0))[0].astype(int).tolist(),
        )
    n_hist = np.bincount(result.n[result.mask], minlength=len(model.remote_params()) + 1)
    stats["cells_by_n"] = {str(i): int(c) for i, c in enumerate(n_hist)}
    return stats


def build_report(
    *,
    model: Model,
    built: str,
    aoi: dict,
    grid: dict,
    mask_info: dict,
    params_status: dict[str, dict],
    params: dict[str, np.ndarray],
    result: ScoreResult,
    sources: list[dict],
    outputs: dict,
    cell_ha: float,
) -> dict:
    return {
        "model": model.id,
        "model_path": str(model.path),
        "built": built,
        "aoi": aoi,
        "grid": grid,
        "mask": mask_info,
        "params": params_status,
        "availability_pct": availability(params, result.mask, model),
        "score": score_stats(result, model, cell_ha),
        "sources": sources,
        "outputs": outputs,
    }


def write_unmapped_csv(path: Path, param: str, rows: list[dict]) -> Path | None:
    """CSV con le colonne della tabella di lookup + superfici, pronto da completare."""
    if not rows or param not in UNMAPPED_TARGET:
        return None
    table, key_col, name_col = UNMAPPED_TARGET[param]
    cols = list(SPECS[table][1]) + ["ha", "ha_bosco", "in_tabella"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            rec = {c: "" for c in cols}
            rec[key_col] = r["value"]
            if name_col:
                rec[name_col] = r.get("name", "")
            rec["ha"] = r["ha"]
            rec["ha_bosco"] = r.get("ha_bosco", "")
            rec["in_tabella"] = "si" if r.get("in_table") else "no"
            w.writerow(rec)
    return path
