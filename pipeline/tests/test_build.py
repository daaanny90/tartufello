"""Build completo su dati locali SINTETICI (configurazioni scritte nel tmp del test).

Codici, attributi e valori sono inventati per il test (sint_*, U_SINT_*, T_SINT_*).
"""

import csv
import json

import numpy as np
import pytest
import rasterio
from shapely.geometry import box

from fiuto_pipeline.build import run_build
from fiuto_pipeline.cli import main
from fiuto_pipeline.errors import FiutoError
from fiuto_pipeline.model import DEFAULT_MODEL_PATH

from .conftest import H_M, W_M, X0, Y0, write_raster, write_text, write_vector

LOOKUP_GEO = """
unit_code,unit_name,vth_class,note,fonte
U_SINT_1,,calcari,,test sintetico
"""
LOOKUP_TEX = """
valore_er,texture_id,note,fonte
TEX_SINT_A,franca,,test sintetico
TEX_SINT_B,argillosa,,test sintetico
"""
LOOKUP_FOR = """
tipo_er,tipo_er_nome,forest_class,hosts,note,fonte
T_SINT_1,Bosco sintetico,latifoglie_fresche,1,,test sintetico
"""


@pytest.fixture
def project(tmp_path):
    d = tmp_path / "dati"
    # DTM 5 m: 450 m a sinistra, 800 m a destra
    z = np.full((int(H_M / 5), int(W_M / 5)), 450.0, dtype="float32")
    z[:, z.shape[1] // 2 :] = 800.0
    write_raster(d / "dtm.tif", z, x0=X0, y1=Y0 + H_M, res=5.0, crs="EPSG:5659", nodata=-9999.0)
    write_raster(
        d / "ph.tif", np.full((40, 80), 7.4, dtype="float32"), x0=X0, y1=Y0 + H_M, res=25.0, crs="EPSG:5659"
    )
    write_vector(
        d / "geo.gpkg",
        [
            {"sint_code": "U_SINT_1", "sint_name": "Calcare sint"},
            {"sint_code": "U_SINT_2", "sint_name": "Da classificare sint"},
        ],
        [box(X0, Y0, X0 + 1500, Y0 + H_M), box(X0 + 1500, Y0, X0 + W_M, Y0 + H_M)],
    )
    write_vector(
        d / "suoli.gpkg",
        [{"sint_tex": "TEX_SINT_A", "sint_caco3": 8.0}, {"sint_tex": "TEX_SINT_B", "sint_caco3": 0.5}],
        [box(X0, Y0, X0 + 1000, Y0 + H_M), box(X0 + 1000, Y0, X0 + W_M, Y0 + H_M)],
    )
    # bosco su 3/4 dell'area, il resto non boscato
    write_vector(d / "bosco.gpkg", [{"sint_tipo": "T_SINT_1"}], [box(X0, Y0, X0 + 1500, Y0 + H_M)])
    lk = tmp_path / "lookups"
    write_text(lk / "geologia_vth.csv", LOOKUP_GEO)
    write_text(lk / "suoli_tessitura.csv", LOOKUP_TEX)
    write_text(lk / "forestale_vth.csv", LOOKUP_FOR)
    write_text(
        tmp_path / "sources.toml",
        f"""
        [defaults]
        crs = "EPSG:5659"
        [sources.dtm]
        status = "da verificare"
        local_path = "{d / "dtm.tif"}"
        [sources.ph]
        status = "ok"
        local_path = "{d / "ph.tif"}"
        [sources.suoli]
        status = "da verificare"
        local_path = "{d / "suoli.gpkg"}"
        [sources.suoli.attributes]
        texture_attr = "sint_tex"
        caco3_attr = "sint_caco3"
        [sources.geologia]
        status = "da verificare"
        local_path = "{d / "geo.gpkg"}"
        [sources.geologia.attributes]
        unit_code_attr = "sint_code"
        unit_name_attr = "sint_name"
        [sources.forestale]
        status = "da verificare"
        local_path = "{d / "bosco.gpkg"}"
        [sources.forestale.attributes]
        forest_type_attr = "sint_tipo"
        """,
    )
    write_text(
        tmp_path / "aoi.toml",
        f"""
        [aoi.sint]
        description = "AOI sintetica di test"
        crs = "EPSG:5659"
        bbox = [{X0}, {Y0}, {X0 + W_M}, {Y0 + H_M}]
        """,
    )
    write_text(
        tmp_path / "build.toml",
        f"""
        model = "{DEFAULT_MODEL_PATH}"
        [grid]
        crs = "EPSG:5659"
        cell_size = 25
        [export]
        minzoom = 12
        maxzoom = 14
        simplification = 1.0
        """,
    )
    return tmp_path


def _run(project, **kw):
    logs = []
    rep = run_build(
        "sint",
        sources_path=project / "sources.toml",
        aoi_path=project / "aoi.toml",
        build_path=project / "build.toml",
        lookup_dir=project / "lookups",
        out_dir=project / "out",
        log=logs.append,
        **kw,
    )
    return rep, "\n".join(logs)


def test_full_build(project, model):
    rep, log = _run(project)
    assert rep["model"] == "vth-v1"
    assert all(v["status"] == "ok" for v in rep["params"].values()), rep["params"]
    assert rep["availability_pct"]["elevation"] == 100.0
    assert rep["mask"]["type"] == "bosco"
    # U_SINT_2 è fuori bosco: va comunque segnalata, con 0 ha in bosco
    un = rep["unmapped"]["bedrock"]
    assert (
        [u["value"] for u in un] == ["U_SINT_2"]
        and un[0]["ha"] == pytest.approx(50.0)
        and un[0]["ha_bosco"] == 0
    )
    assert {s["id"]: s["status"] for s in rep["sources"]}["ph"] == "ok"
    assert "Da classificare per bedrock" in log

    # GeoTIFF: bande con nome, score in millesimi
    with rasterio.open(rep["outputs"]["geotiff"]) as ds:
        assert ds.crs.to_epsg() == 5659 and ds.count == 12
        assert ds.descriptions[:5] == ("score_x1000", "pts", "max", "n", "mask")
        score = ds.read(1)
    # cella in alto a sinistra: bedrock 3, ph 3, caco3 3, texture 3, elev 3, forest 3, hosts 1 -> 19/19
    assert score[0, 0] == 1000
    assert score[0, -1] == 65535  # fuori bosco

    # PMTiles verificato e con metadata del contratto
    exp = rep["outputs"]["export"]
    assert exp["verify"]["features_checked"] > 0
    from pmtiles.reader import MmapSource, Reader

    with open(exp["tiles"]["path"], "rb") as f:
        meta = Reader(MmapSource(f)).metadata()
    assert meta["model"] == "vth-v1" and meta["aoi"] == "sint"
    assert {s["id"] for s in meta["sources"]} == {"dtm", "ph", "suoli", "geologia", "forestale"}
    assert all("verified" in s for s in meta["sources"])

    # CSV dei valori da classificare con le colonne della lookup
    with open(rep["outputs"]["da_classificare_bedrock"], encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert (
        rows[0]["unit_code"] == "U_SINT_2"
        and rows[0]["unit_name"] == "Da classificare sint"
        and rows[0]["vth_class"] == ""
    )
    assert json.loads((project / "out" / "report.json").read_text())["model"] == "vth-v1"


def test_unconfigured_source_is_skipped(project):
    s = (project / "sources.toml").read_text().replace('texture_attr = "sint_tex"', 'texture_attr = ""')
    (project / "sources.toml").write_text(s)
    rep, log = _run(project, tiles=False)
    assert rep["params"]["texture"]["status"] == "saltato"
    assert "texture_attr" in rep["params"]["texture"]["reason"]
    assert "texture: saltato" in log
    assert rep["params"]["caco3"]["status"] == "ok"


def test_no_forest_refused_unless_flag(project):
    s = (project / "sources.toml").read_text()
    s = s.replace(f'local_path = "{project / "dati" / "bosco.gpkg"}"', 'local_path = ""')
    (project / "sources.toml").write_text(s)
    with pytest.raises(FiutoError, match="no-forest-mask"):
        _run(project)
    rep, _ = _run(project, forest_mask=False, tiles=True)
    assert rep["mask"]["type"] == "nessuna"
    from pmtiles.reader import MmapSource, Reader

    with open(rep["outputs"]["export"]["tiles"]["path"], "rb") as f:
        assert "senza maschera" in Reader(MmapSource(f)).metadata()["warning"]


def test_cli_build_and_errors(project, capsys):
    base = [
        "--sources",
        str(project / "sources.toml"),
        "--aoi-file",
        str(project / "aoi.toml"),
        "--build-config",
        str(project / "build.toml"),
        "--lookups",
        str(project / "lookups"),
    ]
    assert main(base + ["build", "--aoi", "nessuna"]) == 1
    assert "non trovata" in capsys.readouterr().err
    assert main(base + ["build", "--aoi", "sint", "--out", str(project / "cli_out"), "--no-tiles"]) == 0
    assert (project / "cli_out" / "report.json").exists()
    assert main(base + ["info"]) == 0
    out = capsys.readouterr().out
    assert "Parametri pronti per il build: bedrock, ph, caco3, texture, elevation, forest_type, hosts" in out


def test_cli_info_on_repo_config(capsys):
    # la configurazione del repo: tutto ancora da verificare, nessun parametro pronto
    assert main(["info"]) == 0
    out = capsys.readouterr().out
    assert "Parametri pronti per il build: nessuno" in out
    assert "[da verificare]" in out and "APPROSSIMATIVA" in out


def test_cli_fetch_refuses_with_exit_2(capsys):
    assert main(["fetch", "geologia"]) == 2
    assert "capabilities geologia" in capsys.readouterr().err


def test_cell_size_outside_range_refused(project):
    s = (project / "build.toml").read_text().replace("cell_size = 25", "cell_size = 5")
    (project / "build.toml").write_text(s)
    with pytest.raises(FiutoError, match="precisione finta"):
        _run(project)


def test_empty_lookups_list_values_to_classify(project):
    """Fase 0: tabelle vuote. Il build elenca le unità trovate anche se poi si ferma."""
    for name in ("geologia_vth", "suoli_tessitura", "forestale_vth"):
        head = (project / "lookups" / f"{name}.csv").read_text().strip().splitlines()[0]
        (project / "lookups" / f"{name}.csv").write_text(head + "\n")
    s = (project / "sources.toml").read_text()
    for sid in ("dtm", "ph"):
        s = s.replace(f'local_path = "{project / "dati" / (sid + ".tif")}"', 'local_path = ""')
    s = s.replace('caco3_attr = "sint_caco3"', 'caco3_attr = ""')
    (project / "sources.toml").write_text(s)
    with pytest.raises(FiutoError, match="Valori da classificare"):
        _run(project)
    with open(project / "out" / "da_classificare_bedrock.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # ordinati per superficie in bosco: U_SINT_1 sta nel bosco, U_SINT_2 no
    assert [r["unit_code"] for r in rows] == ["U_SINT_1", "U_SINT_2"]
    assert rows[0]["unit_name"] == "Calcare sint" and rows[0]["in_tabella"] == "no"
    assert (project / "out" / "da_classificare_forest_type.csv").exists()
    assert (project / "out" / "da_classificare_texture.csv").exists()
