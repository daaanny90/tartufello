"""Normalizzazione dello score: massimi remoti dal modello, minParams, maschera."""

import numpy as np
import pytest

from fiuto_pipeline.errors import ModelError
from fiuto_pipeline.model import NA
from fiuto_pipeline.score import combine
from fiuto_pipeline.score.combine import score_milli


def arr(*vals):
    return np.array(vals, dtype="uint8")


def test_hosts_counts_max_one(model):
    # 4 parametri: tre da 3 punti massimi + hosts (massimo remoto 1)
    p = {
        "ph": arr(3, 3),
        "texture": arr(2, 2),
        "elevation": arr(3, 3),
        "hosts": arr(1, 0),
    }
    r = combine(p, model)
    assert r.max.tolist() == [10, 10]
    assert r.pts.tolist() == [9, 8]
    assert r.n.tolist() == [4, 4]
    assert np.allclose(r.score, [0.9, 0.8])


def test_min_params_cutoff(model):
    p = {
        "ph": arr(3, 3, NA),
        "texture": arr(3, 3, 3),
        "elevation": arr(3, NA, 3),
        "bedrock": arr(3, 3, 3),
    }
    r = combine(p, model)
    assert r.n.tolist() == [4, 3, 3]
    assert np.isfinite(r.score[0]) and r.score[0] == pytest.approx(1.0)
    assert np.isnan(r.score[1]) and np.isnan(r.score[2])
    # pts/max restano: l'app li mostra come "dati insufficienti"
    assert r.pts.tolist() == [12, 9, 9]
    assert r.max.tolist() == [12, 9, 9]


def test_mask_excludes_cells(model):
    p = {k: arr(2, 2) for k in ("ph", "texture", "elevation", "bedrock")}
    mask = np.array([True, False])
    r = combine(p, model, mask)
    assert np.isfinite(r.score[0]) and np.isnan(r.score[1])
    assert r.n.tolist() == [4, 0] and r.pts.tolist() == [8, 0] and r.max.tolist() == [12, 0]


def test_missing_params_are_not_available(model):
    r = combine({"ph": arr(3)}, model)
    assert r.n.tolist() == [1] and np.isnan(r.score[0])


def test_points_above_remote_max_rejected(model):
    with pytest.raises(ModelError):
        combine({"hosts": arr(2)}, model)


def test_non_remote_param_rejected(model):
    with pytest.raises(ModelError):
        combine({"orchids": arr(3)}, model)


def test_score_rounding_half_up():
    # 5/16 = 0.3125 -> 313 (non 312 come con l'arrotondamento al pari)
    assert score_milli(np.array([5]), np.array([16])).tolist() == [313.0]
    assert score_milli(np.array([2]), np.array([3])).tolist() == [667.0]
