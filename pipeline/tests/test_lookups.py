"""Tabelle di lookup: commenti, validazione contro il modello, valori non mappati.

Codici e nomi delle unità sono SINTETICI (U_SINT_*), non codici ER.
"""

import numpy as np
import pytest
from shapely.geometry import box

from fiuto_pipeline.config import Source
from fiuto_pipeline.derive import derive_bedrock, derive_forest, derive_texture, map_categories, map_ints
from fiuto_pipeline.errors import ConfigError, NotConfigured
from fiuto_pipeline.lookups import SPECS, category_map, int_map, load_lookup, norm_key
from fiuto_pipeline.model import NA
from fiuto_pipeline.paths import LOOKUPS_DIR

from .conftest import X0, Y0, write_text, write_vector


def test_shipped_lookups_are_sourced_drafts(model):
    # Le tabelle nel repo contengono solo bozze tratte dai testi dei dataset (Fase 0):
    # ogni riga cita la fonte, è segnata BOZZA e usa categorie valide del modello.
    for name in SPECS:
        lk = load_lookup(name, LOOKUPS_DIR)
        for k, row in lk.rows.items():
            assert row.get("fonte"), f"{name}.csv: '{k}' senza fonte"
            assert "BOZZA" in row.get("note", ""), f"{name}.csv: '{k}' non segnata come BOZZA"
    category_map(load_lookup("geologia_vth", LOOKUPS_DIR), "vth_class", model.categories("bedrock"))
    category_map(load_lookup("suoli_tessitura", LOOKUPS_DIR), "texture_id", model.categories("texture"))
    category_map(load_lookup("forestale_vth", LOOKUPS_DIR), "forest_class", model.categories("forest_type"))
    int_map(load_lookup("forestale_specie", LOOKUPS_DIR), "host", model.remote_max("hosts"))


def test_comments_and_normalization(tmp_path):
    write_text(
        tmp_path / "geologia_vth.csv",
        """
        unit_code,unit_name,vth_class,note,fonte
        # commento: va ignorato
        U_SINT_1 , Calcare sintetico,calcari,,test
        12,Unità numerica sintetica,marne,,test
        U_SINT_3,Da decidere,,,test
        """,
    )
    lk = load_lookup("geologia_vth", tmp_path)
    assert set(lk.rows) == {"U_SINT_1", "12", "U_SINT_3"}
    assert lk.get(12.0)["vth_class"] == "marne"  # attributo numerico letto come float
    assert norm_key("  a ") == "a" and norm_key(float("nan")) is None
    assert lk.mapped_count("vth_class") == 2


def test_unknown_category_is_error(tmp_path, model):
    write_text(
        tmp_path / "geologia_vth.csv", "unit_code,unit_name,vth_class,note,fonte\nU_SINT_1,x,granito,,\n"
    )
    lk = load_lookup("geologia_vth", tmp_path)
    with pytest.raises(ConfigError, match="granito"):
        category_map(lk, "vth_class", model.categories("bedrock"))


def test_duplicate_key_and_missing_column(tmp_path):
    write_text(
        tmp_path / "geologia_vth.csv",
        "unit_code,unit_name,vth_class,note,fonte\nA,x,calcari,,\nA,y,marne,,\n",
    )
    with pytest.raises(ConfigError, match="ripetuto"):
        load_lookup("geologia_vth", tmp_path)
    write_text(tmp_path / "suoli_tessitura.csv", "valore_er,note\n")
    with pytest.raises(ConfigError, match="texture_id"):
        load_lookup("suoli_tessitura", tmp_path)


def test_hosts_above_remote_max_is_error(tmp_path, model):
    write_text(
        tmp_path / "forestale_vth.csv",
        "tipo_er,tipo_er_nome,forest_class,hosts,note,fonte\nT_SINT_1,x,latifoglie_fresche,2,,\n",
    )
    lk = load_lookup("forestale_vth", tmp_path)
    with pytest.raises(ConfigError, match="fuori da 0..1"):
        int_map(lk, "hosts", model.remote_max("hosts"))


def test_map_categories_reports_unmapped_with_area(model):
    codes = np.array([[0, 0, 1], [2, 2, -1]], dtype="int32")
    labels = ["U_SINT_A", "U_SINT_B", "U_SINT_C"]
    mask = np.array([[True, False, True], [True, True, True]])
    pts, unmapped = map_categories(
        codes,
        labels,
        {"U_SINT_A": "calcari"},
        model.categories("bedrock"),
        cell_ha=0.0625,
        mask=mask,
        names={"U_SINT_C": "Unità C sintetica"},
    )
    assert pts.tolist() == [[3, 3, NA], [NA, NA, NA]]
    assert [u["value"] for u in unmapped] == ["U_SINT_C", "U_SINT_B"]  # ordinati per superficie in bosco
    c = unmapped[0]
    assert c["ha"] == 0.125 and c["ha_bosco"] == 0.125 and c["name"] == "Unità C sintetica"
    assert c["in_table"] is False


def test_map_ints_hosts():
    codes = np.array([0, 1, -1], dtype="int32")
    pts, unmapped = map_ints(codes, ["T1", "T2"], {"T1": 1}, cell_ha=1.0)
    assert pts.tolist() == [1, NA, NA]
    assert unmapped == [{"value": "T2", "name": "", "ha": 1.0, "in_table": False}]


# --- derive da vettori sintetici --------------------------------------------------


def _src(sid, path, **attrs):
    return Source(id=sid, crs="EPSG:5659", local_path=str(path), attributes=attrs)


def test_derive_bedrock_end_to_end(tmp_path, grid, model):
    gpkg = write_vector(
        tmp_path / "geo_sint.gpkg",
        [
            {"sint_code": "U_SINT_1", "sint_name": "Calcare sintetico"},
            {"sint_code": "U_SINT_2", "sint_name": "Arenaria sintetica"},
            {"sint_code": "U_SINT_3", "sint_name": "Non in tabella"},
        ],
        [
            box(X0, Y0, X0 + 1000, Y0 + 1000),
            box(X0 + 1000, Y0, X0 + 1500, Y0 + 1000),
            box(X0 + 1500, Y0, X0 + 2000, Y0 + 1000),
        ],
    )
    lk = tmp_path / "lk"
    write_text(
        lk / "geologia_vth.csv",
        "unit_code,unit_name,vth_class,note,fonte\nU_SINT_1,,calcari,,test\nU_SINT_2,,senza_calcio,,test\n",
    )
    src = _src("geologia", gpkg, unit_code_attr="sint_code", unit_name_attr="sint_name")
    mask = np.zeros(grid.shape, dtype=bool)
    mask[:, -10:] = True  # 10 colonne in "bosco" dentro U_SINT_3
    res = derive_bedrock(src, grid, model, mask=mask, lookup_dir=lk)
    a = res.array
    assert a[:, :40].max() == 3 and a[:, :40].min() == 3
    assert (a[:, 40:60] == 0).all()
    assert (a[:, 60:] == NA).all()
    assert len(res.unmapped) == 1
    u = res.unmapped[0]
    assert u["value"] == "U_SINT_3" and u["name"] == "Non in tabella"
    assert u["ha"] == pytest.approx(500 * 1000 / 10_000)
    assert u["ha_bosco"] == pytest.approx(10 * 40 * 0.0625)


def test_derive_without_identifiers_or_lookup(tmp_path, grid, model):
    gpkg = write_vector(tmp_path / "s.gpkg", [{"a": "x"}], [box(X0, Y0, X0 + 100, Y0 + 100)])
    with pytest.raises(NotConfigured, match="texture_attr"):
        derive_texture(_src("suoli", gpkg), grid, model, lookup_dir=tmp_path)
    # lookup vuota: niente punti (tutto 255) ma il valore viene elencato da classificare
    write_text(tmp_path / "suoli_tessitura.csv", "valore_er,texture_id,note,fonte\n")
    res = derive_texture(_src("suoli", gpkg, texture_attr="a"), grid, model, lookup_dir=tmp_path)
    assert (res.array == NA).all()
    assert [u["value"] for u in res.unmapped] == ["x"] and res.unmapped[0]["ha"] == 1.0
    assert "da classificare" in res.detail


def test_wrong_attribute_lists_available_fields(tmp_path, grid, model):
    gpkg = write_vector(tmp_path / "s.gpkg", [{"tess_sint": "X"}], [box(X0, Y0, X0 + 100, Y0 + 100)])
    write_text(tmp_path / "suoli_tessitura.csv", "valore_er,texture_id,note,fonte\nX,franca,,\n")
    with pytest.raises(ConfigError, match="tess_sint"):
        derive_texture(_src("suoli", gpkg, texture_attr="non_esiste"), grid, model, lookup_dir=tmp_path)


def test_derive_forest_type_and_hosts(tmp_path, grid, model):
    gpkg = write_vector(
        tmp_path / "for_sint.gpkg",
        [{"tipo_sint": "T_SINT_1"}, {"tipo_sint": "T_SINT_2"}, {"tipo_sint": "T_SINT_9"}],
        [
            box(X0, Y0, X0 + 500, Y0 + 1000),
            box(X0 + 500, Y0, X0 + 1000, Y0 + 1000),
            box(X0 + 1000, Y0, X0 + 1250, Y0 + 1000),
        ],
    )
    write_text(
        tmp_path / "forestale_vth.csv",
        """
        tipo_er,tipo_er_nome,forest_class,hosts,note,fonte
        T_SINT_1,Faggeta sintetica,latifoglie_fresche,1,,test
        T_SINT_2,Pineta sintetica,altri,,,test
        """,
    )
    src = _src("forestale", gpkg, forest_type_attr="tipo_sint")
    out = derive_forest(src, grid, model, lookup_dir=tmp_path)
    ft, hosts = out["forest_type"].array, out["hosts"].array
    assert (ft[:, :20] == 3).all() and (ft[:, 20:40] == 0).all() and (ft[:, 40:] == NA).all()
    assert (hosts[:, :20] == 1).all() and (hosts[:, 20:] == NA).all()
    assert [u["value"] for u in out["forest_type"].unmapped] == ["T_SINT_9"]
    assert {u["value"] for u in out["hosts"].unmapped} == {"T_SINT_2", "T_SINT_9"}
    t2 = next(u for u in out["hosts"].unmapped if u["value"] == "T_SINT_2")
    assert t2["in_table"] is True  # in tabella ma senza hosts compilato


# --- ospiti dalle specie prevalenti ----------------------------------------------------


def test_combine_hosts_rules():
    from fiuto_pipeline.derive.params import combine_hosts

    # celle: [ospite+?, nonospite+nonospite, nonospite+ignota, assente, ?+ospite, nonospite+assente]
    v1 = np.array([1, 0, 0, NA, NA, 0], dtype="uint8")
    p1 = np.array([1, 1, 1, 0, 1, 1], dtype=bool)
    v2 = np.array([NA, 0, NA, NA, 1, NA], dtype="uint8")
    p2 = np.array([1, 1, 1, 0, 1, 0], dtype=bool)
    out = combine_hosts([v1, v2], [p1, p2])
    assert out.tolist() == [1, 0, NA, NA, 1, 0]


def test_derive_forest_hosts_from_species(tmp_path, grid, model):
    gpkg = write_vector(
        tmp_path / "for_sint.gpkg",
        [
            {
                "tipo_sint": "T1",
                "sp1": "S_OSP",
                "sp2": "S_NO",
                "n1": "Specie ospite sint",
                "n2": "Non ospite sint",
            },
            {
                "tipo_sint": "T1",
                "sp1": "S_NO",
                "sp2": "S_NO",
                "n1": "Non ospite sint",
                "n2": "Non ospite sint",
            },
            {
                "tipo_sint": "T1",
                "sp1": "S_NO",
                "sp2": "S_IGNOTA",
                "n1": "Non ospite sint",
                "n2": "Ignota sint",
            },
        ],
        [
            box(X0, Y0, X0 + 500, Y0 + 1000),
            box(X0 + 500, Y0, X0 + 1000, Y0 + 1000),
            box(X0 + 1000, Y0, X0 + 1500, Y0 + 1000),
        ],
    )
    write_text(tmp_path / "forestale_vth.csv", "tipo_er,tipo_er_nome,forest_class,hosts,note,fonte\n")
    write_text(
        tmp_path / "forestale_specie.csv",
        """
        specie_er,specie_nome,host,note,fonte
        S_OSP,Specie ospite sint,1,BOZZA da rivedere,test
        S_NO,Non ospite sint,0,BOZZA da rivedere,test
        """,
    )
    src = _src(
        "forestale",
        gpkg,
        forest_type_attr="tipo_sint",
        hosts_attrs=["sp1", "sp2"],
        hosts_name_attrs=["n1", "n2"],
    )
    out = derive_forest(src, grid, model, lookup_dir=tmp_path)
    h = out["hosts"]
    assert (h.array[:, :20] == 1).all() and (h.array[:, 20:40] == 0).all()
    assert (h.array[:, 40:60] == NA).all() and (h.array[:, 60:] == NA).all()
    assert h.lookup == "forestale_specie" and h.drafts == 2
    assert [u["value"] for u in h.unmapped] == ["S_IGNOTA"] and h.unmapped[0]["name"] == "Ignota sint"
    assert (out["forest_type"].array == NA).all() and out["forest_type"].lookup == "forestale_vth"


def test_unmapped_csv_uses_species_schema(tmp_path):
    import csv

    from fiuto_pipeline.score import write_unmapped_csv

    rows = [{"value": "S_X", "name": "Specie X", "ha": 1.5, "ha_bosco": 1.0, "in_table": False}]
    p = write_unmapped_csv(tmp_path / "h.csv", "hosts", rows, "forestale_specie")
    rec = list(csv.DictReader(open(p, encoding="utf-8")))[0]
    assert rec["specie_er"] == "S_X" and rec["specie_nome"] == "Specie X" and rec["host"] == ""


def test_draft_count(tmp_path):
    from fiuto_pipeline.lookups import draft_count

    write_text(
        tmp_path / "geologia_vth.csv",
        "unit_code,unit_name,vth_class,note,fonte\nA,,calcari,BOZZA da rivedere,x\nB,,marne,verificata,x\n",
    )
    assert draft_count(load_lookup("geologia_vth", tmp_path)) == 1
