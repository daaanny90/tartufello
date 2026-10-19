"""Poligonizzazione + export PMTiles su un raster SINTETICO minuscolo.

Si rilegge il PMTiles tile per tile (decoder MVT) e si controlla il contratto
`tiles` del modello: chiavi omesse quando il parametro manca, score assente
sotto minParams, metadata con model/built/aoi/sources.
"""

import json

import numpy as np
import pandas as pd
import pytest

from fiuto_pipeline.export import (
    METHOD_GDAL_MBTILES,
    METHOD_GDAL_PMTILES,
    METHOD_NONE,
    available_method,
    decode,
    encode,
    export_vth,
    polygonize,
    verify_pmtiles,
)
from fiuto_pipeline.export.mvt import decode_tile
from fiuto_pipeline.grid import Grid
from fiuto_pipeline.model import NA

META = {
    "model": "vth-v1",
    "built": "2026-01-01T00:00:00+00:00",
    "aoi": "test-sintetico",
    "sources": [{"id": "sint", "status": "sintetico"}],
}


@pytest.fixture
def tiny(model):
    """4x6 celle da 25 m vicino a Calestano (solo per posizionare): tre zone di parametri."""
    g = Grid.from_bounds((579_000, 939_000, 579_150, 939_100), "EPSG:5659", 25.0)
    assert g.shape == (4, 6)
    p = {pid: np.full(g.shape, NA, dtype="uint8") for pid in model.remote_params()}
    # zona A (colonne 0-1): 5 parametri -> score
    for pid, v in (("bedrock", 3), ("ph", 2), ("texture", 3), ("elevation", 3), ("hosts", 1)):
        p[pid][:, 0:2] = v
    # zona B (colonne 2-3): 3 parametri -> niente score
    for pid, v in (("ph", 1), ("elevation", 2), ("forest_type", 0)):
        p[pid][:, 2:4] = v
    # zona C (colonne 4-5): tutti i 7 parametri
    for pid, v in (
        ("bedrock", 0),
        ("ph", 0),
        ("caco3", 3),
        ("texture", 2),
        ("elevation", 1),
        ("forest_type", 3),
        ("hosts", 0),
    ):
        p[pid][:, 4:6] = v
    mask = np.ones(g.shape, dtype=bool)
    mask[3, :] = False  # ultima riga fuori bosco
    return g, p, mask


def test_encode_decode_roundtrip(model, tiny):
    g, p, mask = tiny
    key = encode(p, model, mask)
    assert (key[3] == -1).all()
    back = decode(key[:3], model)
    for pid in model.remote_params():
        assert (back[pid] == p[pid][:3]).all()


def test_polygonize_properties(model, tiny):
    g, p, mask = tiny
    gdf = polygonize(p, mask, g, model)
    assert len(gdf) == 3
    rows = {int(r["n"]): r for r in gdf.drop(columns="geometry").to_dict("records")}
    a, b, c = rows[5], rows[3], rows[7]
    assert a["pts"] == 12 and a["max"] == 13 and a["score"] == pytest.approx(0.923)
    assert pd.isna(b["score"])
    assert c["pts"] == 9 and c["max"] == 19 and c["score"] == pytest.approx(0.474)
    # area: 2 colonne x 3 righe di celle da 625 m2
    assert gdf.geometry.area.round().tolist() == [3750.0] * 3


@pytest.mark.parametrize("method", [METHOD_GDAL_PMTILES, METHOD_GDAL_MBTILES])
def test_export_roundtrip_contract(tmp_path, model, tiny, method):
    if method != METHOD_GDAL_PMTILES and available_method() == METHOD_NONE:
        pytest.skip("GDAL senza driver vettoriali per tile")
    g, p, mask = tiny
    out = export_vth(
        p,
        mask,
        g,
        model,
        tmp_path,
        stem="vth_sint",
        minzoom=10,
        maxzoom=14,
        name="test",
        description="test sintetico",
        metadata=META,
        method=method,
    )
    assert out["tiles"]["method"] == method
    v = out["verify"]  # export_vth verifica già: qui ricontrolliamo a mano
    assert v["min_zoom"] == 10 and v["max_zoom"] == 14
    from pmtiles.reader import MmapSource, Reader, all_tiles

    seen = {}
    with open(tmp_path / "vth_sint.pmtiles", "rb") as f:
        src = MmapSource(f)
        meta = Reader(src).metadata()
        for _zxy, data in all_tiles(src):
            for layer in decode_tile(data):
                assert layer["name"] == "vth"
                for feat in layer["features"]:
                    assert feat["type"] == "polygon"
                    seen[feat["properties"]["n"]] = feat["properties"]
    for k in ("model", "built", "aoi", "sources"):
        assert meta[k] == META[k]
    assert [v["id"] for v in meta["vector_layers"]] == ["vth"]
    assert seen[5] == {
        "score": 0.923,
        "pts": 12,
        "max": 13,
        "n": 5,
        "bedrock": 3,
        "ph": 2,
        "texture": 3,
        "elevation": 3,
        "hosts": 1,
    }
    assert seen[3] == {"pts": 3, "max": 9, "n": 3, "ph": 1, "elevation": 2, "forest_type": 0}  # niente score
    assert seen[7]["score"] == 0.474 and seen[7]["hosts"] == 0 and seen[7]["bedrock"] == 0
    assert set(seen) == {3, 5, 7}


def test_geojsonseq_omits_missing_keys(tmp_path, model, tiny):
    g, p, mask = tiny
    out = export_vth(
        p,
        mask,
        g,
        model,
        tmp_path,
        stem="s",
        minzoom=12,
        maxzoom=13,
        name="t",
        description="t",
        metadata=META,
        method=METHOD_NONE,
    )
    assert out["tiles"]["path"] is None and "tippecanoe" in out["hint"]
    feats = [json.loads(line) for line in open(out["geojsonseq"], encoding="utf-8")]
    assert len(feats) == 3
    b = next(f for f in feats if f["properties"]["n"] == 3)
    assert "score" not in b["properties"] and "bedrock" not in b["properties"]
    lon, lat = b["geometry"]["coordinates"][0][0]
    assert 9.9 < lon < 10.2 and 44.5 < lat < 44.7  # EPSG:4326


def test_verify_detects_contract_violation(tmp_path, model, tiny):
    from fiuto_pipeline.errors import FiutoError
    from fiuto_pipeline.export.tiles import write_pmtiles

    g, p, mask = tiny
    gdf = polygonize(p, mask, g, model).to_crs("EPSG:4326")
    gdf["pts"] = gdf["pts"] + 1  # pts non torna più con la somma dei parametri
    keys = list(model.tile_properties)
    write_pmtiles(
        gdf,
        tmp_path / "bad.pmtiles",
        keys=keys,
        layer="vth",
        minzoom=12,
        maxzoom=12,
        name="bad",
        description="bad",
        metadata=META,
    )
    with pytest.raises(FiutoError, match="pts="):
        verify_pmtiles(tmp_path / "bad.pmtiles", model)


def test_empty_mask_refused(tmp_path, model, tiny):
    from fiuto_pipeline.errors import FiutoError

    g, p, _ = tiny
    with pytest.raises(FiutoError, match="nessun poligono"):
        export_vth(
            p,
            np.zeros(g.shape, bool),
            g,
            model,
            tmp_path,
            stem="e",
            minzoom=12,
            maxzoom=12,
            name="e",
            description="e",
            metadata=META,
            geojsonseq=False,
        )


def test_synthetic_app_fixture_if_present(model):
    """La fixture dell'app (se generata) è conforme e dichiarata sintetica."""
    from pmtiles.reader import MmapSource, Reader

    from fiuto_pipeline.paths import REPO_ROOT

    path = REPO_ROOT / "app" / "e2e" / "fixtures" / "synthetic-vth.pmtiles"
    if not path.exists():
        pytest.skip("fixture non generata (scripts/make_synthetic_fixture.py)")
    v = verify_pmtiles(path, model)
    assert v["features_without_score"] > 0
    with open(path, "rb") as f:
        meta = Reader(MmapSource(f)).metadata()
    assert meta["synthetic"] is True and "SINTETICI" in meta["description"]
