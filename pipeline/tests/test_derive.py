"""Derive da raster e vettori SINTETICI: quota, pH, CaCO3, maschera bosco."""

import warnings

import numpy as np
import pytest
from shapely.geometry import box

from fiuto_pipeline.config import Source
from fiuto_pipeline.derive import derive_caco3, derive_elevation, derive_forest_mask, derive_ph
from fiuto_pipeline.errors import ConfigError, NotConfigured
from fiuto_pipeline.geoio import check_range
from fiuto_pipeline.model import NA

from .conftest import H_M, W_M, X0, Y0, write_raster, write_vector


def _src(sid, path, **attrs):
    return Source(id=sid, crs="EPSG:5659", local_path=str(path), attributes=attrs)


def test_elevation_average_5m_to_25m(tmp_path, grid, model):
    # DTM sintetico a 5 m: metà sinistra 590 m, destra 610 m; una cella mista a cavallo
    w, h = int(W_M / 5), int(H_M / 5)
    z = np.full((h, w), 590.0, dtype="float32")
    z[:, w // 2 :] = 610.0
    z[:, w // 2 - 1] = 650.0  # ultima colonna a 5 m della metà sinistra: media 602 -> 2 punti
    tif = write_raster(
        tmp_path / "dtm_sint.tif", z, x0=X0, y1=Y0 + H_M, res=5.0, crs="EPSG:5659", nodata=-9999.0
    )
    res = derive_elevation(_src("dtm", tif), grid, model)
    a = res.array
    assert a.shape == grid.shape
    assert (a[:, : grid.width // 2 - 1] == 3).all()
    assert (a[:, grid.width // 2 - 1] == 2).all()  # (4*590 + 650)/5 = 602
    assert (a[:, grid.width // 2 :] == 2).all()


def test_elevation_from_other_crs_and_tiles_dir(tmp_path, grid, model):
    # Due tile sintetici in UTM 32N (EPSG:32632) che coprono l'area: il derive li riproietta
    from pyproj import Transformer

    t = Transformer.from_crs("EPSG:5659", "EPSG:32632", always_xy=True)
    minx, miny, maxx, maxy = t.transform_bounds(X0 - 200, Y0 - 200, X0 + W_M + 200, Y0 + H_M + 200)
    midx = (minx + maxx) / 2
    res_m = 10.0
    for name, x0, x1, val in (("a", minx, midx, 1200.0), ("b", midx, maxx, 1700.0)):
        w = int(np.ceil((x1 - x0) / res_m))
        h = int(np.ceil((maxy - miny) / res_m))
        write_raster(
            tmp_path / "tiles" / f"{name}.tif",
            np.full((h, w), val, dtype="float32"),
            x0=x0,
            y1=maxy,
            res=res_m,
            crs="EPSG:32632",
        )
    a = derive_elevation(_src("dtm", tmp_path / "tiles"), grid, model).array
    assert set(np.unique(a).tolist()) <= {0, 1}  # 1200 -> 1, 1700 -> 0
    assert (a != NA).all()
    assert (a[:, :5] == 1).all() and (a[:, -5:] == 0).all()


def test_elevation_partial_coverage_is_na(tmp_path, grid, model):
    z = np.full((40, 40), 300.0, dtype="float32")  # 1 km x 1 km a 25 m: solo metà griglia
    tif = write_raster(tmp_path / "dtm.tif", z, x0=X0, y1=Y0 + H_M, res=25.0, crs="EPSG:5659")
    a = derive_elevation(_src("dtm", tif), grid, model).array
    assert (a[:, :40] == 3).all() and (a[:, 40:] == NA).all()


def test_undeclared_nodata_is_refused(tmp_path, grid, model):
    z = np.full((40, 80), -9999.0, dtype="float32")
    z[:, :10] = 400.0
    tif = write_raster(tmp_path / "dtm.tif", z, x0=X0, y1=Y0 + H_M, res=25.0, crs="EPSG:5659", nodata=None)
    with pytest.raises(ConfigError, match="nodata"):
        derive_elevation(_src("dtm", tif), grid, model)


def test_check_range_few_outliers_become_nan():
    v = np.array([7.0] * 999 + [70.0], dtype="float32")
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        out = check_range(v, 2, 11, "pH", max_bad_share=0.005)
    assert np.isnan(out[-1]) and np.isfinite(out[:-1]).all()


def test_ph_from_raster_with_scale(tmp_path, grid, model):
    # pH sintetico salvato in decimi (72 = 7,2): value_scale = 0.1
    z = np.full((40, 80), 72, dtype="int16")
    z[:, 40:] = 57
    tif = write_raster(tmp_path / "ph.tif", z, x0=X0, y1=Y0 + H_M, res=25.0, crs="EPSG:5659", nodata=-1)
    a = derive_ph(_src("ph", tif, value_scale=0.1), grid, model).array
    assert (a[:, :40] == 3).all() and (a[:, 40:] == 1).all()
    # senza scala i valori sono fuori range: errore che chiede di verificare la scala
    with pytest.raises(ConfigError, match="scala"):
        derive_ph(_src("ph", tif), grid, model)


def test_ph_from_vector_attribute(tmp_path, grid, model):
    gpkg = write_vector(
        tmp_path / "ph_sint.gpkg",
        [{"ph_sint": 6.8}, {"ph_sint": None}],
        [box(X0, Y0, X0 + 1000, Y0 + H_M), box(X0 + 1000, Y0, X0 + W_M, Y0 + H_M)],
    )
    with pytest.raises(NotConfigured, match="ph_attr"):
        derive_ph(_src("ph", gpkg), grid, model)
    a = derive_ph(_src("ph", gpkg, ph_attr="ph_sint"), grid, model).array
    assert (a[:, :40] == 2).all() and (a[:, 40:] == NA).all()


def test_caco3_from_vector(tmp_path, grid, model):
    gpkg = write_vector(
        tmp_path / "suoli_sint.gpkg",
        [{"caco3_sint": 0.0}, {"caco3_sint": 5.0}, {"caco3_sint": 12.5}],
        [
            box(X0, Y0, X0 + 500, Y0 + H_M),
            box(X0 + 500, Y0, X0 + 1000, Y0 + H_M),
            box(X0 + 1000, Y0, X0 + W_M, Y0 + H_M),
        ],
    )
    a = derive_caco3(_src("suoli", gpkg, caco3_attr="caco3_sint"), grid, model).array
    assert (a[:, :20] == 0).all() and (a[:, 20:40] == 2).all() and (a[:, 40:] == 3).all()


def test_forest_mask_any_polygon_and_where(tmp_path, grid):
    gpkg = write_vector(
        tmp_path / "bosco_sint.gpkg",
        [{"cat_sint": "bosco"}, {"cat_sint": "altro"}],
        [box(X0, Y0, X0 + 500, Y0 + 500), box(X0 + 1000, Y0, X0 + 1500, Y0 + 500)],
    )
    m, _ = derive_forest_mask(_src("forestale", gpkg), grid)
    assert m.sum() == 2 * 20 * 20
    m2, detail = derive_forest_mask(_src("forestale", gpkg, mask_where="cat_sint = 'bosco'"), grid)
    assert m2.sum() == 20 * 20 and "where" in detail


def test_vector_in_other_crs_and_multiple_layers(tmp_path, grid):
    import geopandas as gpd

    poly = gpd.GeoSeries([box(X0, Y0, X0 + 500, Y0 + 500)], crs="EPSG:5659").to_crs("EPSG:4326")
    path = tmp_path / "multi.gpkg"
    gpd.GeoDataFrame({"a": [1]}, geometry=poly, crs="EPSG:4326").to_file(path, layer="uno")
    gpd.GeoDataFrame({"a": [1]}, geometry=poly, crs="EPSG:4326").to_file(path, layer="due")
    with pytest.raises(ConfigError, match="più layer"):
        derive_forest_mask(_src("forestale", path), grid)
    m, _ = derive_forest_mask(_src("forestale", path, layer="uno"), grid)
    assert abs(int(m.sum()) - 400) <= 4  # riproiettato da 4326: bordi a ±1 cella


def test_no_local_data_is_not_configured(grid, model, tmp_path):
    src = Source(id="dtm", crs="EPSG:5659", raw_dir=tmp_path)
    with pytest.raises(NotConfigured, match="local_path"):
        derive_elevation(src, grid, model)
    src2 = Source(id="dtm", crs="EPSG:5659", local_path=str(tmp_path / "manca.tif"))
    with pytest.raises(ConfigError, match="non esiste"):
        derive_elevation(src2, grid, model)


def test_text_numeric_attribute_is_refused(tmp_path, grid, model):
    gpkg = write_vector(
        tmp_path / "ph_testo.gpkg",
        [{"ph_sint": "7,2"}, {"ph_sint": "6.8"}],
        [box(X0, Y0, X0 + 1000, Y0 + H_M), box(X0 + 1000, Y0, X0 + W_M, Y0 + H_M)],
    )
    with pytest.raises(ConfigError, match="virgola decimale"):
        derive_ph(_src("ph", gpkg, ph_attr="ph_sint"), grid, model)


def test_nodata_override_when_file_has_none(tmp_path, grid, model):
    # tile come quelli del WCS: nessun nodata dichiarato, -9999 dove non c'è dato
    z = np.full((40, 80), 500.0, dtype="float32")
    z[:, 40:] = -9999.0
    tif = write_raster(tmp_path / "dtm.tif", z, x0=X0, y1=Y0 + H_M, res=25.0, crs="EPSG:5659", nodata=None)
    with pytest.raises(ConfigError, match="nodata"):
        derive_elevation(_src("dtm", tif), grid, model)
    a = derive_elevation(_src("dtm", tif, nodata=-9999), grid, model).array
    assert (a[:, :40] == 3).all() and (a[:, 40:] == NA).all()


def test_forest_mask_where_on_shapefile(tmp_path, grid):
    # con lo Shapefile il filtro deve funzionare anche se il campo non è tra quelli letti
    shp = write_vector(
        tmp_path / "bosco_sint.shp",
        [{"uso_sint": "Bosco"}, {"uso_sint": "Arbusteto"}],
        [box(X0, Y0, X0 + 500, Y0 + 500), box(X0 + 1000, Y0, X0 + 1500, Y0 + 500)],
    )
    m, _ = derive_forest_mask(_src("forestale", shp, mask_where="uso_sint = 'Bosco'"), grid)
    assert m.sum() == 20 * 20
