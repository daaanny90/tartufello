"""Costruzione URL e lettura XML OGC, tutto offline.

Gli XML qui sotto sono campioni SINTETICI scritti per i test (nomi "sint:*"):
non vengono dai server della Regione e non vanno presi come riferimento dei
nomi reali di layer o attributi.
"""

import io
import zipfile
from urllib.parse import parse_qsl, urlsplit

import pytest

from fiuto_pipeline.config import Source
from fiuto_pipeline.errors import ConfigError, FiutoError, NotConfigured
from fiuto_pipeline.fetch import capabilities as caps_mod
from fiuto_pipeline.fetch import choose_method, fetch_wcs, fetch_wfs, ows, run_capabilities
from fiuto_pipeline.fetch.download import _safe_extract

WMS_130 = b"""<?xml version="1.0" encoding="UTF-8"?>
<WMS_Capabilities version="1.3.0" xmlns="http://www.opengis.net/wms">
  <Service><Name>WMS</Name><Title>Servizio sintetico</Title></Service>
  <Capability>
    <Request><GetMap><Format>image/png</Format><Format>image/jpeg</Format></GetMap></Request>
    <Layer>
      <Title>Radice sintetica</Title>
      <CRS>EPSG:4326</CRS>
      <Layer queryable="1"><Name>sint_litologia</Name><Title>Litologia sintetica</Title><CRS>EPSG:5659</CRS></Layer>
      <Layer><Name>sint_altro</Name><Title>Altro</Title><CRS>EPSG:3857</CRS></Layer>
    </Layer>
  </Capability>
</WMS_Capabilities>"""

WFS_200 = b"""<?xml version="1.0" encoding="UTF-8"?>
<wfs:WFS_Capabilities version="2.0.0" xmlns:wfs="http://www.opengis.net/wfs/2.0" xmlns:ows="http://www.opengis.net/ows/1.1">
  <ows:ServiceIdentification><ows:Title>WFS sintetico</ows:Title></ows:ServiceIdentification>
  <ows:OperationsMetadata>
    <ows:Operation name="GetFeature">
      <ows:Parameter name="outputFormat"><ows:AllowedValues>
        <ows:Value>application/gml+xml; version=3.2</ows:Value><ows:Value>application/json</ows:Value>
      </ows:AllowedValues></ows:Parameter>
    </ows:Operation>
    <ows:Constraint name="ImplementsResultPaging"><ows:NoValues/><ows:DefaultValue>TRUE</ows:DefaultValue></ows:Constraint>
  </ows:OperationsMetadata>
  <wfs:FeatureTypeList>
    <wfs:FeatureType><wfs:Name>sint:unita</wfs:Name><wfs:Title>Unita sintetiche</wfs:Title>
      <wfs:DefaultCRS>urn:ogc:def:crs:EPSG::5659</wfs:DefaultCRS></wfs:FeatureType>
  </wfs:FeatureTypeList>
</wfs:WFS_Capabilities>"""

DFT_XSD = b"""<?xml version="1.0" encoding="UTF-8"?>
<xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:gml="http://www.opengis.net/gml/3.2" xmlns:sint="urn:sint" targetNamespace="urn:sint">
  <xsd:complexType name="unitaType">
    <xsd:complexContent><xsd:extension base="gml:AbstractFeatureType"><xsd:sequence>
      <xsd:element name="geom" type="gml:MultiSurfacePropertyType"/>
      <xsd:element name="sint_code" type="xsd:string"/>
      <xsd:element name="sint_caco3" type="xsd:double"/>
    </xsd:sequence></xsd:extension></xsd:complexContent>
  </xsd:complexType>
  <xsd:element name="unita" type="sint:unitaType" substitutionGroup="gml:AbstractFeature"/>
</xsd:schema>"""

WCS_201 = b"""<?xml version="1.0" encoding="UTF-8"?>
<wcs:Capabilities version="2.0.1" xmlns:wcs="http://www.opengis.net/wcs/2.0" xmlns:ows="http://www.opengis.net/ows/2.0">
  <ows:ServiceIdentification><ows:Title>WCS sintetico</ows:Title></ows:ServiceIdentification>
  <wcs:ServiceMetadata><wcs:formatSupported>image/tiff</wcs:formatSupported><wcs:formatSupported>image/png</wcs:formatSupported></wcs:ServiceMetadata>
  <wcs:Contents><wcs:CoverageSummary><wcs:CoverageId>sint__dtm</wcs:CoverageId><wcs:CoverageSubtype>RectifiedGridCoverage</wcs:CoverageSubtype></wcs:CoverageSummary></wcs:Contents>
</wcs:Capabilities>"""

DESCRIBE_COV = b"""<?xml version="1.0" encoding="UTF-8"?>
<wcs:CoverageDescriptions xmlns:wcs="http://www.opengis.net/wcs/2.0" xmlns:gml="http://www.opengis.net/gml/3.2" xmlns:gmlcov="http://www.opengis.net/gmlcov/1.0" xmlns:swe="http://www.opengis.net/swe/2.0">
  <wcs:CoverageDescription gml:id="sint__dtm">
    <gml:boundedBy><gml:Envelope srsName="http://www.opengis.net/def/crs/EPSG/0/5659" axisLabels="E N" srsDimension="2">
      <gml:lowerCorner>500000 900000</gml:lowerCorner><gml:upperCorner>510000 910000</gml:upperCorner>
    </gml:Envelope></gml:boundedBy>
    <wcs:CoverageId>sint__dtm</wcs:CoverageId>
    <gml:domainSet><gml:RectifiedGrid dimension="2"><gml:limits><gml:GridEnvelope>
      <gml:low>0 0</gml:low><gml:high>1999 1999</gml:high></gml:GridEnvelope></gml:limits>
      <gml:offsetVector>5 0</gml:offsetVector><gml:offsetVector>0 -5</gml:offsetVector>
    </gml:RectifiedGrid></gml:domainSet>
    <gmlcov:rangeType><swe:DataRecord><swe:field name="QUOTA_SINT"/></swe:DataRecord></gmlcov:rangeType>
    <wcs:ServiceParameters><wcs:nativeFormat>image/tiff</wcs:nativeFormat></wcs:ServiceParameters>
  </wcs:CoverageDescription>
</wcs:CoverageDescriptions>"""

EXC = b"""<?xml version="1.0"?>
<ows:ExceptionReport xmlns:ows="http://www.opengis.net/ows/1.1" version="2.0.0">
  <ows:Exception exceptionCode="InvalidParameterValue" locator="typeName"><ows:ExceptionText>Feature type sconosciuto</ows:ExceptionText></ows:Exception>
</ows:ExceptionReport>"""


def q(url):
    return parse_qsl(urlsplit(url).query)


def test_build_url_merges_and_replaces():
    url = ows.build_url("https://example.invalid/wms?map=x&service=WFS", ows.capabilities_params("wms"))
    assert q(url) == [("map", "x"), ("SERVICE", "WMS"), ("REQUEST", "GetCapabilities")]


def test_wcs_getcoverage_has_two_subsets():
    params = ows.wcs_getcoverage_params(
        "sint__dtm", axis_x="E", axis_y="N", bbox=(1.0, 2.0, 3.0, 4.0), fmt="image/tiff"
    )
    url = ows.build_url("https://example.invalid/wcs", params)
    subs = [v for k, v in q(url) if k == "SUBSET"]
    assert subs == ["E(1.0,3.0)", "N(2.0,4.0)"]
    assert ("VERSION", "2.0.1") in q(url) and ("COVERAGEID", "sint__dtm") in q(url)


def test_wfs_getfeature_paging_and_bbox_axis_order():
    p = dict(
        ows.wfs_getfeature_params(
            "sint:unita", version="2.0.0", start=2000, count=1000, bbox=(1, 2, 3, 4), crs="EPSG:5659"
        )
    )
    assert p["TYPENAMES"] == "sint:unita" and p["COUNT"] == "1000" and p["STARTINDEX"] == "2000"
    assert p["BBOX"] == "1,2,3,4,urn:ogc:def:crs:EPSG::5659"  # EPSG:5659 è E,N
    # EPSG:4326 in WFS 2.0 è lat,lon: il bbox va girato
    p4326 = dict(
        ows.wfs_getfeature_params(
            "x", version="2.0.0", start=0, count=10, bbox=(10, 44, 11, 45), crs="EPSG:4326"
        )
    )
    assert p4326["BBOX"].startswith("44,10,45,11")
    p11 = dict(ows.wfs_getfeature_params("x", version="1.1.0", start=0, count=10, bbox=None, crs="EPSG:5659"))
    assert "TYPENAME" in p11 and "MAXFEATURES" in p11


def test_split_bbox_aligned():
    # bbox allargato a multipli di 25 m, poi riquadri da 5 km
    tiles = ows.split_bbox((10, 10, 9990, 4990), 5000, align=25)
    assert tiles == [(0, 0, 5000, 5000), (5000, 0, 10000, 5000)]
    assert len(ows.split_bbox((0, 0, 12000, 3000), 5000)) == 3


def test_parse_wms():
    c = ows.parse_wms_capabilities(WMS_130)
    assert c["version"] == "1.3.0" and c["formats"] == ["image/png", "image/jpeg"]
    names = [(lyr["name"], lyr["depth"]) for lyr in c["layers"]]
    assert names == [("", 0), ("sint_litologia", 1), ("sint_altro", 1)]
    assert c["layers"][1]["crs"] == ["EPSG:5659"] and c["layers"][1]["queryable"]


def test_parse_wfs_and_describe_feature_type():
    c = ows.parse_wfs_capabilities(WFS_200)
    assert c["version"] == "2.0.0" and c["paging"] is True
    assert c["feature_types"][0]["name"] == "sint:unita"
    assert "application/json" in c["output_formats"]
    s = ows.parse_describe_feature_type(DFT_XSD)
    assert s["unita"] == [
        ("geom", "MultiSurfacePropertyType"),
        ("sint_code", "string"),
        ("sint_caco3", "double"),
    ]


def test_parse_wcs_and_describe_coverage():
    c = ows.parse_wcs_capabilities(WCS_201)
    assert c["coverages"] == [{"id": "sint__dtm", "title": ""}] and c["formats"] == [
        "image/png",
        "image/tiff",
    ]
    d = ows.parse_describe_coverage(DESCRIBE_COV)[0]
    assert d["id"] == "sint__dtm" and d["axis_labels"] == ["E", "N"]
    assert d["srs"].endswith("/5659") and d["fields"] == ["QUOTA_SINT"]
    assert d["grid_high"] == "1999 1999" and d["offsets"] == ["5 0", "0 -5"]


def test_exception_report_is_error():
    assert "sconosciuto" in ows.exception_message(ows.parse_xml(EXC))
    with pytest.raises(ValueError, match="sconosciuto"):
        ows.parse_wfs_capabilities(EXC)
    with pytest.raises(ValueError, match="XML"):
        ows.parse_xml(b"<html><body>non xml")


def test_number_returned():
    assert ows.number_returned(b'<wfs:FeatureCollection numberMatched="10" numberReturned="7">') == 7
    assert ows.number_returned(b"<x/>") is None


# --- comandi senza rete ------------------------------------------------------------


class FakeResp:
    def __init__(self, content):
        self.content = content


def test_run_capabilities_offline(monkeypatch, tmp_path):
    def fake_get(sess, url, params=None, stream=False):
        d = dict(params)
        if d.get("REQUEST") == "GetCapabilities":
            return FakeResp({"WMS": WMS_130, "WFS": WFS_200}[d["SERVICE"]])
        if d.get("REQUEST") == "DescribeFeatureType":
            return FakeResp(DFT_XSD)
        raise AssertionError(d)

    monkeypatch.setattr(caps_mod, "get", fake_get)
    src = Source(
        id="sint",
        endpoints={"wms": "https://example.invalid/wms", "wfs": "https://example.invalid/wfs"},
        raw_dir=tmp_path,
    )
    out = io.StringIO()
    res = run_capabilities(src, out=out)
    text = out.getvalue()
    assert "sint_litologia | Litologia sintetica | si" in text
    assert "sint_code: string" in text  # nome con prefisso risolto
    assert res["wfs"]["schemas"]["sint:unita"][1] == ("sint_code", "string")
    assert (tmp_path / "sint" / "capabilities_wms.xml").exists()


def test_capabilities_without_endpoints_refuses(tmp_path):
    with pytest.raises(ConfigError, match="--url"):
        run_capabilities(Source(id="x", raw_dir=tmp_path), out=io.StringIO())


def test_fetch_refuses_without_identifiers(tmp_path):
    src = Source(
        id="dtm", crs="EPSG:5659", endpoints={"wcs": "https://example.invalid/wcs"}, raw_dir=tmp_path
    )
    with pytest.raises(NotConfigured, match="niente da scaricare"):
        choose_method(src, None)
    with pytest.raises(NotConfigured, match="wcs_coverage_id"):
        fetch_wcs(src, (0, 0, 1, 1))
    src2 = Source(
        id="geo", crs="EPSG:5659", endpoints={"wfs": "https://example.invalid/wfs"}, raw_dir=tmp_path
    )
    with pytest.raises(NotConfigured, match="wfs_typename"):
        fetch_wfs(src2, (0, 0, 1, 1))
    assert not (tmp_path / "dtm").exists()  # nessun file creato


def test_fetch_wcs_xml_error_is_reported(monkeypatch, tmp_path):
    from fiuto_pipeline.fetch import download

    class Raw(io.BytesIO):
        decode_content = False

    class StreamResp:
        def __init__(self, body):
            self.raw = Raw(body)

    monkeypatch.setattr(download, "get", lambda *a, **k: StreamResp(EXC))
    src = Source(
        id="dtm",
        crs="EPSG:5659",
        endpoints={"wcs": "https://example.invalid/wcs"},
        raw_dir=tmp_path,
        service={
            "wcs_version": "2.0.1",
            "wcs_coverage_id": "sint__dtm",
            "wcs_axis_x": "E",
            "wcs_axis_y": "N",
            "wcs_format": "image/tiff",
        },
    )
    with pytest.raises(FiutoError, match="XML invece del raster"):
        fetch_wcs(src, (0, 0, 100, 100), log=lambda *a: None)
    assert not list((tmp_path / "dtm" / "wcs" / "sint__dtm").glob("*.tif"))


def test_zip_slip_is_blocked(tmp_path):
    zpath = tmp_path / "evil.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("../fuori.txt", "x")
    with pytest.raises(FiutoError, match="sospetto"):
        _safe_extract(zpath, tmp_path / "out")
    assert not (tmp_path / "fuori.txt").exists()


def _gml_page(start, n):
    """Pagina GetFeature GML 3.2 SINTETICA con n poligoni quadrati."""
    members = []
    for i in range(start, start + n):
        x = 600000 + i * 100
        members.append(f"""
  <wfs:member><sint:unita gml:id="unita.{i}">
    <sint:sint_code>U_SINT_{i}</sint:sint_code>
    <sint:geom><gml:Polygon gml:id="p{i}" srsName="urn:ogc:def:crs:EPSG::5659"><gml:exterior><gml:LinearRing>
      <gml:posList>{x} 930000 {x + 100} 930000 {x + 100} 930100 {x} 930100 {x} 930000</gml:posList>
    </gml:LinearRing></gml:exterior></gml:Polygon></sint:geom>
  </sint:unita></wfs:member>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0" xmlns:gml="http://www.opengis.net/gml/3.2"
  xmlns:sint="urn:sint" numberMatched="unknown" numberReturned="{n}">{"".join(members)}
</wfs:FeatureCollection>""".encode()


def test_fetch_wfs_paging_offline(monkeypatch, tmp_path):
    import pyogrio

    from fiuto_pipeline.fetch import download

    calls = []

    def fake_get(sess, url, params=None, stream=False):
        d = dict(params)
        calls.append(d)
        start, count = int(d["STARTINDEX"]), int(d["COUNT"])
        total = 5
        return FakeResp(_gml_page(start, max(0, min(count, total - start))))

    monkeypatch.setattr(download, "get", fake_get)
    src = Source(
        id="geologia",
        crs="EPSG:5659",
        endpoints={"wfs": "https://example.invalid/wfs"},
        raw_dir=tmp_path,
        service={"wfs_typename": "sint:unita", "wfs_page_size": 2},
    )
    out = fetch_wfs(src, (600000, 930000, 601000, 931000), log=lambda *a: None)
    assert [c["STARTINDEX"] for c in calls] == ["0", "2", "4"]  # l'ultima pagina ha 1 feature < 2: stop
    assert all(c["BBOX"].endswith("urn:ogc:def:crs:EPSG::5659") for c in calls)
    df = pyogrio.read_dataframe(out)
    assert sorted(df["sint_code"]) == [f"U_SINT_{i}" for i in range(5)]
    assert df.crs.to_epsg() == 5659
    assert src.data_path() == out  # il build lo trova dal manifest
    # seconda volta: tutto dalla cache, nessuna richiesta
    calls.clear()
    fetch_wfs(src, (600000, 930000, 601000, 931000), log=lambda *a: None)
    assert calls == []


# --- WCS 1.0.0 (server ArcGIS) e ritentativi HTTP ------------------------------------

DESCRIBE_COV_100 = b"""<?xml version="1.0" encoding="UTF-8"?>
<CoverageDescription xmlns="http://www.opengis.net/wcs" xmlns:gml="http://www.opengis.net/gml" version="1.0.0">
<CoverageOffering>
  <name>SINT_DTM</name><label>DTM sintetico</label>
  <domainSet><spatialDomain>
    <gml:Envelope srsName="EPSG:7791"><gml:pos dimension="2">500000 4900000</gml:pos><gml:pos dimension="2">510000 4910000</gml:pos></gml:Envelope>
    <gml:RectifiedGrid srsName="EPSG:7791" dimension="2"><gml:limits><gml:GridEnvelope><gml:low>0 0</gml:low><gml:high>1999 1999</gml:high></gml:GridEnvelope></gml:limits>
      <gml:offsetVector dimension="2">5 0</gml:offsetVector><gml:offsetVector dimension="2">0 -5</gml:offsetVector></gml:RectifiedGrid>
  </spatialDomain></domainSet>
  <rangeSet><RangeSet><name>r</name><axisDescription><AxisDescription><name>Band</name><values><singleValue>1</singleValue></values></AxisDescription></axisDescription></RangeSet></rangeSet>
  <supportedCRSs><requestResponseCRSs>EPSG:7791</requestResponseCRSs><nativeCRSs>EPSG:7791</nativeCRSs></supportedCRSs>
  <supportedFormats nativeFormat="GeoTIFF"><formats>GeoTIFF</formats><formats>PNG</formats></supportedFormats>
</CoverageOffering>
</CoverageDescription>"""


def test_wcs100_params_and_describe():
    p = dict(
        ows.wcs100_getcoverage_params("SINT_DTM", crs="EPSG:7791", bbox=(1, 2, 3, 4), res=5, fmt="GeoTIFF")
    )
    assert p["VERSION"] == "1.0.0" and p["COVERAGE"] == "SINT_DTM" and p["CRS"] == "EPSG:7791"
    assert p["BBOX"] == "1,2,3,4" and p["RESX"] == "5.0" and p["RESY"] == "5.0"
    assert ("COVERAGE", "X") in ows.describe_coverage_params("X", "1.1.2")
    assert ("COVERAGEID", "X") in ows.describe_coverage_params("X", "2.0.1")
    d = ows.parse_describe_coverage(DESCRIBE_COV_100)
    assert len(d) == 1
    d = d[0]
    assert d["id"] == "SINT_DTM" and d["title"] == "DTM sintetico" and d["srs"] == "EPSG:7791"
    assert d["native_crs"] == ["EPSG:7791"] and d["formats"] == ["GeoTIFF", "PNG"]
    assert d["offsets"] == ["5 0", "0 -5"] and d["lower"] == "500000 4900000"


def _tif_bytes(count: int, dtype: str) -> bytes:
    import numpy as np
    from rasterio.io import MemoryFile
    from rasterio.transform import from_origin

    with MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            width=4,
            height=4,
            count=count,
            dtype=dtype,
            crs="EPSG:7791",
            transform=from_origin(0, 100, 25, 25),
        ) as ds:
            ds.write(np.ones((count, 4, 4), dtype=dtype))
        return mem.read()


class _Raw(io.BytesIO):
    decode_content = False


class _StreamResp:
    def __init__(self, body):
        self.raw = _Raw(body)


def _wcs100_source(tmp_path):
    return Source(
        id="dtm",
        crs="EPSG:7791",
        endpoints={"wcs": "https://example.invalid/wcs"},
        raw_dir=tmp_path,
        service={
            "wcs_version": "1.0.0",
            "wcs_coverage_id": "SINT_DTM",
            "wcs_format": "GeoTIFF",
            "wcs_res": 25,
        },
    )


def test_fetch_wcs100_tiles(monkeypatch, tmp_path):
    from fiuto_pipeline.fetch import download

    calls = []

    def fake_get(sess, url, params=None, stream=False):
        calls.append(dict(params))
        return _StreamResp(_tif_bytes(1, "float32"))

    monkeypatch.setattr(download, "get", fake_get)
    src = _wcs100_source(tmp_path)
    out = fetch_wcs(src, (0, 0, 7000, 3000), tile_size=5000, log=lambda *a: None)
    assert len(list(out.glob("*.tif"))) == 2 and len(calls) == 2
    assert all(c["VERSION"] == "1.0.0" and c["CRS"] == "EPSG:7791" and c["RESX"] == "25.0" for c in calls)
    assert src.data_path() == out
    calls.clear()
    fetch_wcs(src, (0, 0, 7000, 3000), tile_size=5000, log=lambda *a: None)
    assert calls == []  # dalla cache


def test_fetch_wcs_refuses_rgba_image(monkeypatch, tmp_path):
    from fiuto_pipeline.fetch import download

    monkeypatch.setattr(download, "get", lambda *a, **k: _StreamResp(_tif_bytes(4, "uint8")))
    with pytest.raises(FiutoError, match="immagine"):
        fetch_wcs(_wcs100_source(tmp_path), (0, 0, 100, 100), log=lambda *a: None)
    assert not list((tmp_path / "dtm").rglob("*.tif"))


def test_fetch_wcs_requires_version_specific_ids(tmp_path):
    src = _wcs100_source(tmp_path)
    src.service.pop("wcs_res")
    with pytest.raises(NotConfigured, match="wcs_res"):
        fetch_wcs(src, (0, 0, 1, 1))
    src.service["wcs_version"] = "1.1.2"
    with pytest.raises(ConfigError, match="non gestito"):
        fetch_wcs(src, (0, 0, 1, 1))


class _Resp:
    def __init__(self, status, url="https://example.invalid/x"):
        self.status_code, self.url, self.text = status, url, "errore"

    def close(self):
        pass


class _FlakySession:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def get(self, url, params=None, timeout=None, stream=False):
        self.calls += 1
        o = self.outcomes.pop(0)
        if isinstance(o, Exception):
            raise o
        return o


def test_http_get_retries(monkeypatch):
    import requests

    from fiuto_pipeline.fetch import http

    monkeypatch.setattr(http, "_sleep", lambda s: None)
    sess = _FlakySession([requests.ConnectionError("chiusa"), _Resp(503), _Resp(200)])
    assert http.get(sess, "https://example.invalid/x").status_code == 200 and sess.calls == 3
    sess = _FlakySession([requests.ConnectionError("chiusa")] * (http.RETRIES + 1))
    with pytest.raises(FiutoError, match="tentativi"):
        http.get(sess, "https://example.invalid/x")
    sess = _FlakySession([_Resp(404)])
    with pytest.raises(FiutoError, match="HTTP 404"):
        http.get(sess, "https://example.invalid/x")
    assert sess.calls == 1  # 404 non si ritenta
