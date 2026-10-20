"""prepare suoli: triangolo USDA, medie 0-30 cm e unione carta + Excel.

Shapefile ed Excel qui sono SINTETICI: stessi nomi di colonna del pacchetto
regionale (configurabili), valori inventati per il test.
"""

import pytest
from shapely.geometry import box

from fiuto_pipeline.config import Source
from fiuto_pipeline.errors import ConfigError, NotConfigured
from fiuto_pipeline.prepare import aggregate_profile, prepare_suoli, usda_texture
from fiuto_pipeline.prepare.suoli import OUT_LAYER, REQUIRED

from .conftest import X0, Y0, write_vector


@pytest.mark.parametrize(
    "sand,silt,clay,cls",
    [
        (92, 4, 4, "sand"),
        (82, 12, 6, "loamy sand"),
        (65, 25, 10, "sandy loam"),
        (40, 40, 20, "loam"),
        (30, 60, 10, "silt loam"),
        (5, 88, 7, "silt"),
        (60, 15, 25, "sandy clay loam"),
        (30, 35, 35, "clay loam"),
        (10, 60, 30, "silty clay loam"),
        (50, 5, 45, "sandy clay"),
        (5, 50, 45, "silty clay"),
        (30, 25, 45, "clay"),
    ],
)
def test_usda_texture_all_classes(sand, silt, clay, cls):
    assert usda_texture(sand, silt, clay) == cls


def test_usda_texture_normalizes_and_handles_missing():
    assert usda_texture(400, 400, 200) == "loam"  # g/kg -> normalizzato
    assert usda_texture(None, 40, 20) is None
    assert usda_texture(0, 0, 0) is None


def test_usda_classes_match_model_categories(model):
    # ogni classe prodotta ha una categoria del modello con lo stesso nome usda
    usda = {c["usda"] for c in model.param("texture")["categories"]}
    produced = {
        usda_texture(*t)
        for t in [
            (92, 4, 4),
            (82, 12, 6),
            (65, 25, 10),
            (40, 40, 20),
            (30, 60, 10),
            (5, 88, 7),
            (60, 15, 25),
            (30, 35, 35),
            (10, 60, 30),
            (50, 5, 45),
            (5, 50, 45),
            (30, 25, 45),
        ]
    }
    assert produced == usda


def test_aggregate_profile_weights_0_30():
    hz = [
        {"top": 0, "bottom": 10, "sand": 40, "silt": 40, "clay": 20, "caco3": 10, "ph": 8.0},
        {"top": 10, "bottom": 50, "sand": 20, "silt": 40, "clay": 40, "caco3": 0, "ph": 7.0},
        {"top": 50, "bottom": 120, "sand": 90, "silt": 5, "clay": 5, "caco3": 30, "ph": 6.0},  # fuori strato
    ]
    a = aggregate_profile(hz)
    assert a["n"] == 2 and a["depth_cm"] == 30
    assert a["ph"] == pytest.approx((8.0 * 10 + 7.0 * 20) / 30, abs=0.01)
    assert a["caco3"] == pytest.approx(10 * 10 / 30, abs=0.01)
    assert a["clay"] == pytest.approx((20 * 10 + 40 * 20) / 30, abs=0.1)
    assert a["usda"] == usda_texture(a["sand"], a["silt"], a["clay"])
    # un valore mancante usa solo gli orizzonti dove c'è
    hz[0]["ph"] = None
    assert aggregate_profile(hz)["ph"] == 7.0
    assert aggregate_profile([])["ph"] is None


CFG = {
    "shp_join": "SINT_DEL",
    "soils_sheet": "suoli_sint",
    "soils_join": "DEL",
    "soil_code": "COD",
    "soil_name": "NOME",
    "soil_perc": "PERC",
    "soil_site": "SITO",
    "sites_sheet": "siti_sint",
    "site_id": "SITO",
    "top": "DA",
    "bottom": "A",
    "sand": "SAB",
    "silt": "LIM",
    "clay": "ARG",
    "caco3": "CAL",
    "ph": "PH",
}


def _xlsx(path, soils, sites):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "suoli_sint"
    ws.append(["DEL", "COD", "NOME", "PERC", "SITO"])
    for r in soils:
        ws.append(r)
    ws2 = wb.create_sheet("siti_sint")
    ws2.append(["SITO", "DA", "A", "SAB", "LIM", "ARG", "CAL", "PH"])
    for r in sites:
        ws2.append(r)
    wb.save(path)


def test_prepare_suoli_end_to_end(tmp_path):
    import pyogrio

    raw = tmp_path / "raw" / "suoli"
    raw.mkdir(parents=True)
    write_vector(
        raw / "carta_sint.shp",
        [{"SINT_DEL": 1.0}, {"SINT_DEL": 2.0}, {"SINT_DEL": 3.0}],
        [
            box(X0, Y0, X0 + 100, Y0 + 100),
            box(X0 + 100, Y0, X0 + 200, Y0 + 100),
            box(X0 + 200, Y0, X0 + 300, Y0 + 100),
        ],
    )
    _xlsx(
        raw / "profili_sint.xlsx",
        soils=[
            ["1", "SOIL_A", "Suolo A sint", 70, "10"],
            ["1", "SOIL_B", "Suolo B sint", 30, "20"],
            ["2", "SOIL_B", "Suolo B sint", 60, "20"],
            ["3", "SOIL_C", "Suolo C sint", 100, None],  # senza sito: niente valori
        ],
        sites=[
            ["10", 0, 30, 40, 40, 20, 12.0, 8.1],
            ["20", 0, 15, 10, 60, 30, 0.0, 6.0],
            ["20", 15, 60, 10, 60, 30, 2.0, 6.4],
        ],
    )
    src = Source(id="suoli", crs="EPSG:5659", prepare=dict(CFG), raw_dir=tmp_path / "raw", base_dir=tmp_path)
    out = prepare_suoli(src, log=lambda *a: None)
    df = pyogrio.read_dataframe(out, layer=OUT_LAYER).sort_values("SINT_DEL").reset_index(drop=True)
    assert df.loc[0, "suolo_prev"] == "SOIL_A" and df.loc[0, "perc_prev"] == 70
    assert (
        df.loc[0, "ph_0_30"] == 8.1 and df.loc[0, "caco3_0_30"] == 12.0 and df.loc[0, "usda_0_30"] == "loam"
    )
    assert df.loc[1, "ph_0_30"] == pytest.approx(6.2) and df.loc[1, "caco3_0_30"] == pytest.approx(1.0)
    assert df.loc[1, "usda_0_30"] == "silty clay loam"
    assert df.loc[2, "suolo_prev"] == "SOIL_C" and df.loc[2, "ph_0_30"] != df.loc[2, "ph_0_30"]  # NaN
    assert src.data_path() == out  # il build lo trova dal manifest
    assert src.manifest()["method"] == "prepare"


def test_prepare_suoli_refuses_missing_config_or_columns(tmp_path):
    src = Source(id="suoli", raw_dir=tmp_path, prepare={})
    with pytest.raises(NotConfigured, match=REQUIRED[0]):
        prepare_suoli(src, log=lambda *a: None)
    raw = tmp_path / "suoli"
    raw.mkdir()
    write_vector(raw / "c.shp", [{"ALTRO": 1.0}], [box(X0, Y0, X0 + 10, Y0 + 10)])
    _xlsx(raw / "p.xlsx", soils=[], sites=[])
    src = Source(id="suoli", raw_dir=tmp_path, prepare=dict(CFG))
    with pytest.raises(ConfigError, match="SINT_DEL"):
        prepare_suoli(src, log=lambda *a: None)
