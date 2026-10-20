"""Valutatore delle regole ordinate contro le soglie di model/vth-v1.json.

I valori attesi vengono dalla tabella del brief (§4.1) con gli intervalli
semiaperti decisi nel modello: se il modello cambia, questi test lo dicono.
"""

import numpy as np
import pytest

from fiuto_pipeline.errors import ModelError
from fiuto_pipeline.model import NA, classify, points_for, validate_rules


@pytest.mark.parametrize(
    "value,points",
    [(4.0, 0), (5.69, 0), (5.7, 1), (6.79, 1), (6.8, 2), (7.1, 2), (7.19, 2), (7.2, 3), (8.3, 3)],
)
def test_ph(model, value, points):
    assert points_for(value, model.rules("ph")) == points


@pytest.mark.parametrize(
    "value,points",
    [(0, 3), (599.9, 3), (600, 2), (999.9, 2), (1000, 1), (1600, 1), (1600.1, 0), (2100, 0)],
)
def test_elevation(model, value, points):
    assert points_for(value, model.rules("elevation")) == points


@pytest.mark.parametrize(
    "value,points",
    [(0, 0), (0.01, 1), (0.99, 1), (1, 2), (3, 2), (5, 2), (5.01, 3), (40, 3)],
)
def test_caco3(model, value, points):
    assert points_for(value, model.rules("caco3")) == points


@pytest.mark.parametrize(
    "value,points",
    [(0, 0), (5, 1), (14.99, 1), (15, 2), (29.99, 2), (30, 3), (45, 3), (60, 3), (60.01, 2), (90, 2)],
)
def test_ca_exch(model, value, points):
    # non è remoto, ma le regole sono le stesse che userà l'app
    assert points_for(value, model.rules("ca_exch")) == points


def test_vectorized_matches_scalar_and_nan_is_na(model):
    vals = np.array([[5.7, np.nan], [7.2, 6.8]], dtype="float32")
    out = model.classify("ph", vals)
    assert out.dtype == np.uint8
    assert out.tolist() == [[1, NA], [3, 2]]
    assert points_for(None, model.rules("ph")) is None


def test_float32_input_at_threshold(model):
    # i raster arrivano in float32: 7.2 diventa 7.1999998 e 5.7 diventa 5.6999998.
    # Devono comunque prendere i punti della soglia (arrotondamento a 6 decimali).
    ph32 = np.array([5.7, 6.8, 7.2], dtype="float32")
    assert model.classify("ph", ph32).tolist() == [1, 2, 3]
    caco3_32 = np.array([1.0, 5.0, 5.1], dtype="float32")
    assert model.classify("caco3", caco3_32).tolist() == [2, 2, 3]
    # media di celle a 600 m con rumore di calcolo
    assert model.classify("elevation", np.array([599.99999997, 1000.0000001])).tolist() == [2, 1]


def test_first_match_wins_and_fallback():
    rules = [{"gte": 10, "points": 3}, {"gte": 5, "points": 2}, {"points": 0}]
    assert classify(np.array([12, 7, 1, -5]), rules).tolist() == [3, 2, 0, 0]


def test_no_fallback_leaves_na():
    rules = [{"gt": 0, "lt": 10, "points": 1}]
    assert classify(np.array([5, 10, -1]), rules).tolist() == [1, NA, NA]


def test_unknown_rule_key_is_rejected():
    with pytest.raises(ModelError):
        validate_rules([{"between": [1, 2], "points": 1}])
    with pytest.raises(ModelError):
        validate_rules([{"gt": 1}])


def test_model_v2_remote_params_and_max(model):
    remote = model.remote_params()
    assert model.id == "vth-v2"
    assert remote == ["bedrock", "ph", "caco3", "texture", "elevation", "forest_type"]
    assert "hosts" not in remote and "hosts" not in model.tile_properties
    assert all(model.remote_max(p) == 3 for p in remote)
    assert model.min_params == 4
    assert model.categories("forest_type") == {"termofile": 3, "mesofile": 2, "umidi": 1, "altri": 0}
    assert set(remote) <= set(model.tile_properties)


def test_model_v1_still_loads(model_v1):
    remote = model_v1.remote_params()
    assert remote == ["bedrock", "ph", "caco3", "texture", "elevation", "forest_type", "hosts"]
    assert model_v1.remote_max("hosts") == 1
    assert set(remote) <= set(model_v1.tile_properties)


def test_v1_v2_same_numeric_rules(model, model_v1):
    for pid in ("ph", "caco3", "elevation", "ca_exch"):
        assert model.rules(pid) == model_v1.rules(pid)
