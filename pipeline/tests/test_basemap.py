"""Basemap offline: rilievo, curve, unione dei PMTiles, query REST, comando completo.

Dati SINTETICI: DTM a cono o a piano, linee e punti inventati, attributi "sint_*".
Nessuna chiamata di rete: i fetcher sono sostituiti nei test.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest
from affine import Affine
from shapely.geometry import LineString

from fiuto_pipeline.basemap.contours import contour_lines, smooth
from fiuto_pipeline.basemap.hillshade import hillshade, write_hillshade_pmtiles, zoom_resolution
from fiuto_pipeline.basemap.vector import Part, check_parts, merge_pmtiles, write_part, zoom_split
from fiuto_pipeline.errors import FiutoError

from .conftest import H_M, W_M, X0, Y0, write_raster, write_text, write_vector

# lon/lat sintetici in Appennino, per i tile
LON0, LAT0 = 10.10, 44.60


def _pmtiles(path):
    from pmtiles.reader import MmapSource, Reader, all_tiles

    with open(path, "rb") as f:
        src = MmapSource(f)
        r = Reader(src)
        return r.header(), r.metadata(), list(all_tiles(src))


# --- rilievo ------------------------------------------------------------------------


def test_hillshade_flat_is_cos_altitude_and_edges_invalid():
    gray, valid = hillshade(np.full((20, 30), 500.0), 10.0)
    assert not valid[0].any() and not valid[-1].any() and not valid[:, 0].any() and not valid[:, -1].any()
    assert valid[1:-1, 1:-1].all()
    assert (gray[valid] == round(255 * math.cos(math.radians(45)))).all()  # 180
    assert (gray[~valid] == 0).all()


def test_hillshade_sun_from_northwest():
    rows, cols = np.mgrid[0:20, 0:20].astype("float64")
    # righe crescenti = verso sud, colonne crescenti = verso est
    faces_nw = (rows + cols) * 5.0  # scende verso nord-ovest: guarda il sole
    faces_se = -(rows + cols) * 5.0
    g_nw, v = hillshade(faces_nw, 10.0)
    g_se, _ = hillshade(faces_se, 10.0)
    assert g_nw[v].min() > 180 > g_se[v].max()


def test_hillshade_nodata_spreads_to_neighbours():
    z = np.full((10, 10), 100.0)
    z[5, 5] = np.nan
    _, valid = hillshade(z, 10.0)
    assert not valid[4:7, 4:7].any() and valid[2, 2]


def test_zoom_resolution():
    assert zoom_resolution(0) == pytest.approx(156543.03, rel=1e-6)
    assert zoom_resolution(15) == pytest.approx(4.777, rel=1e-3)


def test_write_hillshade_pmtiles(tmp_path):
    from pmtiles.tile import TileType

    z = np.add.outer(np.arange(400.0), np.arange(400.0)) * 3.0 + 400.0  # 4 km x 4 km
    z[:40, :40] = np.nan
    gray, valid = hillshade(z, 10.0)
    t = Affine(10.0, 0, 590_000.0, 0, -10.0, 4_940_000.0)  # EPSG:7791, metri
    res = write_hillshade_pmtiles(
        gray,
        valid,
        t,
        "EPSG:7791",
        tmp_path / "r.pmtiles",
        minzoom=11,
        maxzoom=14,
        metadata={"attribution": "sint"},
    )
    header, meta, tiles = _pmtiles(tmp_path / "r.pmtiles")
    assert header["tile_type"] in (TileType.WEBP, TileType.PNG)
    assert header["max_zoom"] == 14 == res["max_zoom"]
    # a z11 l'area è ~50 px: GDAL non scrive quell'overview e il risultato lo dice
    assert header["min_zoom"] == res["min_zoom"] == 12 and "non scritti" in res["note"]
    assert {zxy[0] for zxy, _ in tiles} == {12, 13, 14}
    assert meta["attribution"] == "sint" and meta["format"] == res["format"].lower()
    _check_alpha(tiles, res["format"])


def _check_alpha(tiles, fmt):
    """Tile pieni: 3 bande (GDAL toglie l'alfa); con nodata: 4 bande, alfa 0 o 255."""
    import warnings

    from rasterio.errors import NotGeoreferencedWarning
    from rasterio.io import MemoryFile

    alphas = set()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        for _zxy, data in tiles:
            with MemoryFile(data) as mf, mf.open() as ds:
                assert ds.count in (3, 4)
                if ds.count == 4:
                    alphas |= set(np.unique(ds.read(4)).tolist())
    assert alphas <= {0, 255} and 0 in alphas


# --- curve di livello -----------------------------------------------------------------


def _cone(n=201, cell=10.0, top=1000.0):
    c = (n - 1) / 2
    rows, cols = np.mgrid[0:n, 0:n].astype("float64")
    r = np.hypot(rows - c, cols - c) * cell
    t = Affine(cell, 0, 0.0, 0, -cell, n * cell)
    return top - r * 0.5, t  # pendenza 50%


def test_contours_on_cone():
    z, t = _cone()
    lines = contour_lines(z, t, interval=10, major_every=50, min_length=100, simplify=0)
    eles = sorted({e for e, _, _ in lines})
    assert all(e % 10 == 0 for e in eles)
    assert all(m == (e % 50 == 0) for e, m, _ in lines)
    assert all(g.length >= 100 for _, _, g in lines)
    # quota e -> cerchio di raggio 2 * (1000 - e); interi dentro la griglia sopra 500 m
    for e, _, g in lines:
        if 500 < e <= 950:
            assert g.length == pytest.approx(2 * math.pi * 2 * (1000 - e), rel=0.02)
    # 990 m: raggio 20 m, 126 m di curva -> resta; la cima (1000) è un punto
    assert max(eles) == 990


def test_contours_drop_short_fragments():
    z, t = _cone()
    short = {e for e, _, _ in contour_lines(z, t, min_length=0, simplify=0)}
    long_ = {e for e, _, _ in contour_lines(z, t, min_length=400, simplify=0)}
    # min_length 400 m -> raggio minimo ~64 m -> quote sopra ~968 m scartate
    assert max(short) > 968 >= max(long_)


def test_smooth_keeps_nodata():
    z = np.full((9, 9), 100.0)
    z[4, 4] = 200.0
    z[0, 0] = np.nan
    s = smooth(z)
    assert np.isnan(s[0, 0]) and np.isfinite(s[0, 1])
    assert 100 < s[4, 4] < 200 and s[4, 4] == np.nanmax(s)
    assert s[0, 1] == pytest.approx(100.0)  # il nodata vicino non abbassa la media


def test_contours_empty_on_nodata():
    z = np.full((10, 10), np.nan)
    assert contour_lines(z, Affine(10, 0, 0, 0, -10, 100)) == []


# --- unione dei PMTiles -----------------------------------------------------------------


def _lines_gdf(n, **cols):
    import geopandas as gpd

    geoms = [LineString([(LON0 + 0.002 * i, LAT0), (LON0 + 0.002 * i, LAT0 + 0.01)]) for i in range(n)]
    return gpd.GeoDataFrame({k: v[:n] for k, v in cols.items()}, geometry=geoms, crs="EPSG:4326")


def test_check_parts_rejects_overlapping_zooms():
    g = _lines_gdf(2, ele=[100, 110])
    check_parts([Part("contours", g, 10, 12), Part("contours", g, 13, 15), Part("roads", g, 10, 15)])
    with pytest.raises(ValueError, match="sovrapposti"):
        check_parts([Part("contours", g, 10, 13), Part("contours", g, 13, 15)])


def test_merge_pmtiles_layers_and_zoom_split(tmp_path):
    import pandas as pd

    from fiuto_pipeline.export.mvt import decode_tile, layer_names

    contours = _lines_gdf(4, ele=[100, 110, 150, 160])
    contours["major"] = pd.array([False, False, True, False], dtype="bool")
    roads = _lines_gdf(3, kind=["strada", "sint_carrareccia", "sint_sentiero"])
    parts = zoom_split("contours", contours, contours["major"].to_numpy(), minzoom=11, split=13, maxzoom=14)
    parts.append(Part("roads", roads, 11, 14))
    check_parts(parts)
    paths = [write_part(p, tmp_path / f"{i}.pmtiles") for i, p in enumerate(parts)]
    res = merge_pmtiles(
        paths, tmp_path / "base.pmtiles", {"fiuto_basemap": True, "aoi": "sint"}, {"roads": "sint"}
    )
    header, meta, tiles = _pmtiles(tmp_path / "base.pmtiles")
    assert (header["min_zoom"], header["max_zoom"]) == (11, 14)
    assert meta["fiuto_basemap"] is True and meta["aoi"] == "sint"
    vl = {v["id"]: v for v in meta["vector_layers"]}
    assert set(vl) == {"contours", "roads"} and vl["roads"]["description"] == "sint"
    assert (vl["contours"]["minzoom"], vl["contours"]["maxzoom"]) == (11, 14)
    assert res["tiles"] == len(tiles) and set(res["tiles_per_layer"]) == {"contours", "roads"}
    for (z, _x, _y), data in tiles:
        names = layer_names(data)
        assert sorted(names) == ["contours", "roads"]
        ct = next(layer for layer in decode_tile(data) if layer["name"] == "contours")
        eles = {f["properties"]["ele"] for f in ct["features"]}
        if z < 13:
            assert eles == {150}  # sotto z13 solo le maggiori
        else:
            assert eles == {100, 110, 150, 160}
        assert {f["value_types"]["major"] for f in ct["features"]} == {"bool"}


def test_merge_pmtiles_refuses_duplicate_layer_in_tile(tmp_path):
    g = _lines_gdf(2, ele=[100, 110])
    a = write_part(Part("contours", g, 12, 12), tmp_path / "a.pmtiles")
    b = write_part(Part("contours", g, 12, 12), tmp_path / "b.pmtiles")
    with pytest.raises(FiutoError, match="ripetuti"):
        merge_pmtiles([a, b], tmp_path / "x.pmtiles", {})


def test_write_part_skips_empty(tmp_path):
    import geopandas as gpd

    empty = gpd.GeoDataFrame({"kind": []}, geometry=[], crs="EPSG:4326")
    assert write_part(Part("roads", empty, 10, 15), tmp_path / "e.pmtiles") is None
    with pytest.raises(FiutoError):
        merge_pmtiles([], tmp_path / "x.pmtiles", {})


# --- ArcGIS REST ------------------------------------------------------------------------


class _Resp:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def _feature(i):
    return {
        "type": "Feature",
        "properties": {"OBJECTID": i, "sint_nome": f"n{i}"},
        "geometry": {"type": "Point", "coordinates": [LON0 + i * 1e-3, LAT0]},
    }


def test_arcgis_query_params():
    from fiuto_pipeline.fetch.download import arcgis_query_params

    p = dict(arcgis_query_params((1.0, 2.0, 3.0, 4.0), in_epsg=7791, fields=["a", "b"], start=20, count=10))
    assert p["geometry"] == "1.0,2.0,3.0,4.0" and p["inSR"] == "7791" and p["outSR"] == "4326"
    assert p["outFields"] == "a,b" and p["resultOffset"] == "20" and p["resultRecordCount"] == "10"
    assert p["f"] == "geojson" and p["orderByFields"] == "OBJECTID"


def test_fetch_arcgis_layer_pages_and_cache(tmp_path, monkeypatch):
    from fiuto_pipeline.config import Source
    from fiuto_pipeline.fetch import download

    data = [_feature(i) for i in range(5)]
    calls = []

    def fake_get(sess, url, params=None, stream=False):
        p = dict(params)
        calls.append((url, p["resultOffset"]))
        start, n = int(p["resultOffset"]), int(p["resultRecordCount"])
        return _Resp({"type": "FeatureCollection", "features": data[start : start + n]})

    monkeypatch.setattr(download, "get", fake_get)
    src = Source(
        id="sint_rest",
        crs="EPSG:7791",
        endpoints={"rest": "https://example.invalid/MapServer"},
        raw_dir=tmp_path,
    )
    g = download.fetch_arcgis_layer(
        src, 7, (0, 0, 1, 1), fields=["sint_nome"], page_size=2, log=lambda *a: None
    )
    assert len(g) == 5 and list(g["sint_nome"]) == [f"n{i}" for i in range(5)] and g.crs.to_epsg() == 4326
    assert [c[1] for c in calls] == ["0", "2", "4"] and calls[0][
        0
    ] == "https://example.invalid/MapServer/7/query"
    calls.clear()
    g2 = download.fetch_arcgis_layer(
        src, 7, (0, 0, 1, 1), fields=["sint_nome"], page_size=2, log=lambda *a: None
    )
    assert calls == [] and len(g2) == 5  # dalla cache


def test_fetch_arcgis_layer_error(tmp_path, monkeypatch):
    from fiuto_pipeline.config import Source
    from fiuto_pipeline.fetch import download

    monkeypatch.setattr(download, "get", lambda *a, **k: _Resp({"error": {"code": 400, "message": "sint"}}))
    src = Source(
        id="sint_rest",
        crs="EPSG:7791",
        endpoints={"rest": "https://example.invalid/MapServer"},
        raw_dir=tmp_path,
    )
    with pytest.raises(FiutoError, match="errore ArcGIS"):
        download.fetch_arcgis_layer(src, 1, (0, 0, 1, 1), fields=[], log=lambda *a: None)


# --- attribuzione e bbox di scarico -------------------------------------------------------


def test_attribution_cc_by_3_and_credit():
    from fiuto_pipeline.build import attribution
    from fiuto_pipeline.config import Source

    text = attribution(
        [
            Source(id="a", title="Sint A - dettaglio", license="CC BY 4.0 (catalogo)"),
            Source(id="b", title="Sint B (codice)", license="CC BY 3.0 (catalogo)"),
            Source(id="c", title="Sint A - altro", license="CC BY 4.0"),
        ],
        credit="Elaborazione fiuto.",
    )
    assert text == "Dati © Regione Emilia-Romagna, CC BY 4.0: Sint A; CC BY 3.0: Sint B. Elaborazione fiuto."


def test_fetch_bbox_margin_in_metres():
    from fiuto_pipeline.config import AOIConfig
    from fiuto_pipeline.grid import fetch_bbox

    a = AOIConfig(name="sint", bbox=(X0, Y0, X0 + W_M, Y0 + H_M), crs="EPSG:5659")
    b = fetch_bbox(a, "EPSG:5659", 100.0)
    assert b == (X0 - 100, Y0 - 100, X0 + W_M + 100, Y0 + H_M + 100)
    g0 = fetch_bbox(a, "EPSG:4326", 0.0)
    g1 = fetch_bbox(a, "EPSG:4326", 1000.0)
    # 1 km di margine: circa 0,009° di latitudine, non 1000 gradi
    assert 0.007 < g0[1] - g1[1] < 0.011 and 0.010 < g0[0] - g1[0] < 0.016


# --- comando completo ------------------------------------------------------------------


@pytest.fixture
def bm_project(tmp_path):
    d = tmp_path / "dati"
    n_r, n_c = int(H_M / 5), int(W_M / 5)
    rows, cols = np.mgrid[0:n_r, 0:n_c].astype("float32")
    r = np.hypot((rows - n_r / 2) * 5, (cols - n_c / 2) * 5)
    z = (900.0 - 0.3 * r).astype("float32")  # collina sintetica
    write_raster(d / "dtm.tif", z, x0=X0, y1=Y0 + H_M, res=5.0, crs="EPSG:5659", nodata=-9999.0)
    write_vector(
        d / "sentieri.gpkg",
        [{"sint_nome": "Sentiero sint", "sint_num": "001", "sint_cls": "SC", "sint_diff": "D1"}],
        [LineString([(X0 + 100, Y0 + 100), (X0 + 1900, Y0 + 900)])],
    )
    write_text(
        tmp_path / "sources.toml",
        f"""
        [sources.dtm]
        title = "DTM sint - edizione"
        status = "ok"
        license = "CC BY 4.0 (sint)"
        crs = "EPSG:5659"
        local_path = "{(d / "dtm.tif").as_posix()}"
        [sources.dtm.attributes]
        band = 1

        [sources.sentieri]
        title = "Sentieri sint"
        status = "ok"
        license = "CC BY 4.0 (sint)"
        crs = "EPSG:4326"
        [sources.sentieri.endpoints]
        wfs = "https://example.invalid/wfs"
        [sources.sentieri.service]
        wfs_typename = "sint:percorsi"
        [sources.sentieri.attributes]
        name_attr = "sint_nome"
        ref_attr = "sint_num"
        kind_attr = "sint_cls"
        difficulty_attr = "sint_diff"

        [sources.dbtr]
        title = "Topo sint - strade"
        status = "ok"
        license = "CC BY 4.0 (sint)"
        crs = "EPSG:5659"
        [sources.dbtr.endpoints]
        rest = "https://example.invalid/MapServer"
        [sources.dbtr.attributes]
        roads_layers = {{ strada = 1, carrareccia = 2 }}
        water_layer = 3
        water_name_attr = "sint_acqua"
        places_layer = 4
        places_name_attr = "sint_loc"
        places_kind_attr = "sint_tipo"

        [sources.dbtr_sentieri]
        title = "Topo sint sentieri"
        status = "ok"
        license = "CC BY 3.0 (sint)"
        crs = "EPSG:5659"
        [sources.dbtr_sentieri.endpoints]
        rest = "https://example.invalid/MapServer"
        [sources.dbtr_sentieri.attributes]
        roads_layers = {{ sentiero = 5 }}
        """,
    )
    write_text(
        tmp_path / "aoi.toml",
        f"""
        [aoi.sint]
        description = "area sintetica"
        crs = "EPSG:5659"
        bbox = [{X0}, {Y0}, {X0 + W_M}, {Y0 + H_M}]
        """,
    )
    return tmp_path


def _fake_rest(src, layer, bbox, *, fields, force=False, page_size=1000, log=print):
    import geopandas as gpd

    def lines(k):
        return [LineString([(X0 + 50 + 300 * i, Y0 + 50), (X0 + 50 + 300 * i, Y0 + 950)]) for i in range(k)]

    if layer in (1, 2, 5):
        return gpd.GeoDataFrame({"OBJECTID": range(3)}, geometry=lines(3), crs="EPSG:5659").to_crs(4326)
    if layer == 3:
        g = gpd.GeoDataFrame({"sint_acqua": ["Rio sint", None]}, geometry=lines(2), crs="EPSG:5659")
        return g.to_crs(4326)
    raise FiutoError("HTTP 500 sint")  # località: il layer manca e va detto


def test_run_basemap(bm_project, monkeypatch):
    from fiuto_pipeline.basemap import BasemapConfig, run_basemap
    from fiuto_pipeline.export.mvt import decode_tile
    from fiuto_pipeline.fetch import download

    calls = []

    def fake_wfs(src, bbox, *, force=False, page_size=None, log=print):
        calls.append((src.id, bbox))
        return bm_project / "dati" / "sentieri.gpkg"

    monkeypatch.setattr(download, "fetch_wfs", fake_wfs)
    monkeypatch.setattr(download, "fetch_arcgis_layer", _fake_rest)
    cfg = BasemapConfig(minzoom=12, maxzoom=14, minor_minzoom=13, roads_minor_minzoom=13)
    logs = []
    rep = run_basemap(
        "sint",
        sources_path=bm_project / "sources.toml",
        aoi_path=bm_project / "aoi.toml",
        raw_dir=bm_project / "raw",
        out_dir=bm_project / "out",
        config=cfg,
        log=logs.append,
    )
    # trails: bbox in lon/lat (la sorgente è in EPSG:4326)
    assert calls and calls[0][0] == "sentieri" and 9 < calls[0][1][0] < 12 and 43 < calls[0][1][1] < 46

    # rilievo
    rh, rmeta, rtiles = _pmtiles(bm_project / "out" / "rilievo_sint.pmtiles")
    assert rh["max_zoom"] == 14 and rtiles
    # area di 2 x 1 km: a z12 è un francobollo e GDAL salta l'overview, il report lo dice
    assert rh["min_zoom"] == 12 or "non scritti" in rep["rilievo"]["note"]
    assert rmeta["aoi"] == "sint" and rmeta["attribution"].startswith(
        "Dati © Regione Emilia-Romagna, CC BY 4.0: DTM sint"
    )

    # base
    _h, meta, tiles = _pmtiles(bm_project / "out" / "base_sint.pmtiles")
    assert meta["fiuto_basemap"] is True and meta["aoi"] == "sint"
    assert meta["attribution"] == (
        "Dati © Regione Emilia-Romagna, CC BY 4.0: DTM sint, Sentieri sint, Topo sint; "
        "CC BY 3.0: Topo sint sentieri. Elaborazione fiuto."
    )
    assert set(meta["missing"]) == {"places"} and "HTTP 500" in meta["missing"]["places"]
    vl = {v["id"]: v for v in meta["vector_layers"]}
    assert set(vl) == {"contours", "trails", "roads", "water"}
    assert set(vl["trails"]["fields"]) == {"name", "ref", "kind", "difficulty"}
    assert set(vl["contours"]["fields"]) == {"ele", "major"}
    seen = {}
    for (z, _x, _y), data in tiles:
        for layer in decode_tile(data):
            for f in layer["features"]:
                seen.setdefault((layer["name"], z >= 13), []).append(f["properties"])
    assert all(p["major"] for p in seen[("contours", False)])
    assert any(not p["major"] for p in seen[("contours", True)])
    assert {p["ele"] % 10 for p in seen[("contours", True)]} == {0}
    assert {p["kind"] for p in seen[("roads", False)]} == {"strada"}
    assert {p["kind"] for p in seen[("roads", True)]} == {"strada", "carrareccia", "sentiero"}
    t = seen[("trails", True)][0]
    assert t == {"name": "Sentiero sint", "ref": "001", "kind": "SC", "difficulty": "D1"}
    water_names = {p.get("name") for p in seen[("water", True)]}
    assert water_names == {"Rio sint", None}  # nome vuoto: proprietà assente

    saved = json.loads((bm_project / "out" / "basemap_sint.json").read_text())
    assert saved["base"]["missing"] == rep["base"]["missing"] and saved["rilievo"]["bytes"] > 0


def test_run_basemap_without_dtm(bm_project):
    from fiuto_pipeline.basemap import run_basemap
    from fiuto_pipeline.errors import NotConfigured

    src = (bm_project / "sources.toml").read_text()
    (bm_project / "sources.toml").write_text(src.replace('local_path = "', 'local_path_old = "'))
    with pytest.raises(NotConfigured):
        run_basemap(
            "sint",
            sources_path=bm_project / "sources.toml",
            aoi_path=bm_project / "aoi.toml",
            raw_dir=bm_project / "raw",
            out_dir=bm_project / "out",
            log=lambda *a: None,
        )


def test_cli_has_basemap():
    from fiuto_pipeline.cli import _parser

    a = _parser().parse_args(["basemap", "--aoi", "sint", "--only", "base"])
    assert a.cmd == "basemap" and a.aoi == "sint" and a.only == "base" and not a.force
