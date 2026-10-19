"""Richieste OGC (WMS/WFS/WCS): costruzione dei parametri e lettura dell'XML.

Solo libreria standard (ElementTree). I tag si confrontano senza namespace,
così lo stesso codice regge versioni diverse dei servizi (WMS 1.1.1/1.3.0,
WFS 1.x/2.0, WCS 1.x/2.0).
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pyproj import CRS

# --- URL --------------------------------------------------------------------


def build_url(base: str, params: list[tuple[str, str]]) -> str:
    """Aggiunge i parametri all'URL base (sostituisce quelli omonimi, senza badare a maiuscole)."""
    parts = urlsplit(base)
    names = {k.upper() for k, _ in params}
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.upper() not in names]
    query += [(k, str(v)) for k, v in params]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query, safe=",:()"), parts.fragment))


def capabilities_params(service: str) -> list[tuple[str, str]]:
    # niente VERSION: il server risponde con la sua versione più alta
    return [("SERVICE", service.upper()), ("REQUEST", "GetCapabilities")]


def describe_feature_type_params(typename: str, version: str = "2.0.0") -> list[tuple[str, str]]:
    key = "TYPENAMES" if version.startswith("2") else "TYPENAME"
    return [("SERVICE", "WFS"), ("VERSION", version), ("REQUEST", "DescribeFeatureType"), (key, typename)]


def describe_coverage_params(coverage_id: str, version: str = "2.0.1") -> list[tuple[str, str]]:
    return [
        ("SERVICE", "WCS"),
        ("VERSION", version),
        ("REQUEST", "DescribeCoverage"),
        ("COVERAGEID", coverage_id),
    ]


def crs_urn(crs: str) -> str:
    c = CRS.from_user_input(crs)
    epsg = c.to_epsg()
    if epsg is None:
        raise ValueError(f"CRS senza codice EPSG: {crs}")
    return f"urn:ogc:def:crs:EPSG::{epsg}"


def bbox_param(bbox: tuple[float, float, float, float], crs: str) -> str:
    """BBOX per WFS 2.0 nell'ordine degli assi del CRS (per EPSG:5659 è E,N)."""
    minx, miny, maxx, maxy = bbox
    c = CRS.from_user_input(crs)
    first = c.axis_info[0].direction.lower() if c.axis_info else "east"
    if first in ("north", "south"):
        minx, miny, maxx, maxy = miny, minx, maxy, maxx
    return f"{minx!r},{miny!r},{maxx!r},{maxy!r},{crs_urn(crs)}"


def wfs_getfeature_params(
    typename: str,
    *,
    version: str,
    start: int,
    count: int,
    bbox: tuple[float, float, float, float] | None,
    crs: str,
    output_format: str | None = None,
) -> list[tuple[str, str]]:
    v2 = version.startswith("2")
    params = [
        ("SERVICE", "WFS"),
        ("VERSION", version),
        ("REQUEST", "GetFeature"),
        ("TYPENAMES" if v2 else "TYPENAME", typename),
        ("COUNT" if v2 else "MAXFEATURES", str(count)),
        ("STARTINDEX", str(start)),
        ("SRSNAME", crs_urn(crs)),
    ]
    if bbox is not None:
        params.append(("BBOX", bbox_param(bbox, crs)))
    if output_format:
        params.append(("OUTPUTFORMAT", output_format))
    return params


def wcs_getcoverage_params(
    coverage_id: str,
    *,
    axis_x: str,
    axis_y: str,
    bbox: tuple[float, float, float, float],
    fmt: str,
) -> list[tuple[str, str]]:
    """GetCoverage WCS 2.0.1 con due SUBSET (stessa unità e CRS nativo della coverage)."""
    minx, miny, maxx, maxy = bbox
    return [
        ("SERVICE", "WCS"),
        ("VERSION", "2.0.1"),
        ("REQUEST", "GetCoverage"),
        ("COVERAGEID", coverage_id),
        ("SUBSET", f"{axis_x}({minx!r},{maxx!r})"),
        ("SUBSET", f"{axis_y}({miny!r},{maxy!r})"),
        ("FORMAT", fmt),
    ]


def split_bbox(
    bbox: tuple[float, float, float, float], size: float, align: float | None = None
) -> list[tuple[float, float, float, float]]:
    """Divide un bbox in riquadri da `size` (allineati a multipli di `align` se dato)."""
    minx, miny, maxx, maxy = bbox
    if align:
        minx = math.floor(minx / align) * align
        miny = math.floor(miny / align) * align
        maxx = math.ceil(maxx / align) * align
        maxy = math.ceil(maxy / align) * align
    out = []
    y = miny
    while y < maxy:
        x = minx
        y1 = min(y + size, maxy)
        while x < maxx:
            x1 = min(x + size, maxx)
            out.append((x, y, x1, y1))
            x = x1
        y = y1
    return out


# --- XML ---------------------------------------------------------------------


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag.split(":")[-1]


def kids(el: ET.Element, name: str) -> list[ET.Element]:
    return [c for c in el if local(c.tag) == name]


def kid(el: ET.Element | None, *path: str) -> ET.Element | None:
    for name in path:
        if el is None:
            return None
        found = kids(el, name)
        el = found[0] if found else None
    return el


def text(el: ET.Element | None, *path: str) -> str:
    e = kid(el, *path) if path else el
    return (e.text or "").strip() if e is not None else ""


def walk(el: ET.Element, name: str):
    for e in el.iter():
        if local(e.tag) == name:
            yield e


def attr(el: ET.Element, name: str) -> str:
    for k, v in el.attrib.items():
        if local(k) == name:
            return v
    return ""


def parse_xml(data: bytes | str) -> ET.Element:
    if isinstance(data, str):
        data = data.encode("utf-8")
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        snippet = data[:200].decode("utf-8", "replace")
        raise ValueError(f"la risposta non è XML valido ({exc}): {snippet!r}") from exc


def exception_message(root: ET.Element) -> str | None:
    """Testo di un ServiceExceptionReport / ows:ExceptionReport, se lo è."""
    if local(root.tag) not in ("ServiceExceptionReport", "ExceptionReport"):
        return None
    msgs = []
    for e in root.iter():
        if local(e.tag) in ("ServiceException", "ExceptionText") and (e.text or "").strip():
            code = attr(e, "code") or attr(e, "exceptionCode")
            msgs.append(f"{code + ': ' if code else ''}{e.text.strip()}")
        elif local(e.tag) == "Exception" and not msgs:
            code = attr(e, "exceptionCode")
            if code:
                msgs.append(code)
    return "; ".join(msgs) or "eccezione senza testo"


def _version(root: ET.Element) -> str:
    return root.attrib.get("version", "")


def parse_wms_capabilities(data: bytes | str) -> dict:
    root = parse_xml(data)
    exc = exception_message(root)
    if exc:
        raise ValueError(f"il server ha risposto con un errore: {exc}")
    cap = kid(root, "Capability")
    getmap = kid(cap, "Request", "GetMap")
    formats = [text(f) for f in kids(getmap, "Format")] if getmap is not None else []
    layers: list[dict] = []

    def visit(el: ET.Element, depth: int) -> None:
        crs = [text(c) for c in kids(el, "CRS")] + [text(c) for c in kids(el, "SRS")]
        layers.append(
            {
                "name": text(el, "Name"),
                "title": text(el, "Title"),
                "crs": crs,
                "depth": depth,
                "queryable": el.attrib.get("queryable", "") in ("1", "true"),
            }
        )
        for child in kids(el, "Layer"):
            visit(child, depth + 1)

    for top in kids(cap, "Layer") if cap is not None else []:
        visit(top, 0)
    return {
        "service": "WMS",
        "version": _version(root),
        "title": text(root, "Service", "Title"),
        "formats": formats,
        "layers": layers,
    }


def parse_wfs_capabilities(data: bytes | str) -> dict:
    root = parse_xml(data)
    exc = exception_message(root)
    if exc:
        raise ValueError(f"il server ha risposto con un errore: {exc}")
    types = []
    ftl = kid(root, "FeatureTypeList")
    for ft in kids(ftl, "FeatureType") if ftl is not None else []:
        default = text(ft, "DefaultCRS") or text(ft, "DefaultSRS") or text(ft, "SRS")
        other = [text(o) for o in kids(ft, "OtherCRS") + kids(ft, "OtherSRS")]
        types.append(
            {"name": text(ft, "Name"), "title": text(ft, "Title"), "default_crs": default, "other_crs": other}
        )
    output_formats: list[str] = []
    paging = None
    for op in walk(root, "Operation"):
        if attr(op, "name") == "GetFeature":
            for p in kids(op, "Parameter"):
                if attr(p, "name").lower() == "outputformat":
                    output_formats += [text(v) for v in walk(p, "Value")]
    for c in walk(root, "Constraint"):
        if attr(c, "name") == "ImplementsResultPaging":
            paging = text(c, "DefaultValue").upper() == "TRUE"
    if not output_formats:  # WFS 1.0
        output_formats = [local(c.tag) for rf in walk(root, "ResultFormat") for c in rf]
    return {
        "service": "WFS",
        "version": _version(root),
        "title": text(root, "ServiceIdentification", "Title") or text(root, "Service", "Title"),
        "feature_types": types,
        "output_formats": output_formats,
        "paging": paging,
    }


def parse_wcs_capabilities(data: bytes | str) -> dict:
    root = parse_xml(data)
    exc = exception_message(root)
    if exc:
        raise ValueError(f"il server ha risposto con un errore: {exc}")
    coverages = []
    for cs in walk(root, "CoverageSummary"):  # 1.1 / 2.0
        cid = text(cs, "CoverageId") or text(cs, "Identifier")
        if cid:
            coverages.append({"id": cid, "title": text(cs, "Title")})
    for cb in walk(root, "CoverageOfferingBrief"):  # 1.0
        coverages.append({"id": text(cb, "name"), "title": text(cb, "label")})
    formats = [text(f) for f in walk(root, "formatSupported")] or [
        text(f) for f in walk(root, "SupportedFormat")
    ]
    return {
        "service": "WCS",
        "version": _version(root),
        "title": text(root, "ServiceIdentification", "Title"),
        "coverages": coverages,
        "formats": sorted(set(formats)),
    }


def parse_describe_feature_type(data: bytes | str) -> dict[str, list[tuple[str, str]]]:
    """Schema XSD -> {nome feature type: [(attributo, tipo), ...]}."""
    root = parse_xml(data)
    exc = exception_message(root)
    if exc:
        raise ValueError(f"il server ha risposto con un errore: {exc}")
    complex_types = {ct.attrib.get("name"): ct for ct in kids(root, "complexType")}

    def fields(ct: ET.Element) -> list[tuple[str, str]]:
        seq = None
        for e in ct.iter():
            if local(e.tag) == "sequence":
                seq = e
                break
        if seq is None:
            return []
        return [
            (e.attrib.get("name", e.attrib.get("ref", "")), local(e.attrib.get("type", "")))
            for e in kids(seq, "element")
        ]

    out = {}
    for el in kids(root, "element"):
        name = el.attrib.get("name", "")
        t = el.attrib.get("type")
        if t and local(t) in complex_types:
            out[name] = fields(complex_types[local(t)])
        else:
            inline = kid(el, "complexType")
            if inline is not None:
                out[name] = fields(inline)
    if not out:  # nessun element globale: elenca i complexType
        out = {n: fields(ct) for n, ct in complex_types.items() if n}
    return out


def parse_describe_coverage(data: bytes | str) -> list[dict]:
    root = parse_xml(data)
    exc = exception_message(root)
    if exc:
        raise ValueError(f"il server ha risposto con un errore: {exc}")
    out = []
    for cd in walk(root, "CoverageDescription"):
        env = next(walk(cd, "Envelope"), None)
        grid_env = next(walk(cd, "GridEnvelope"), None)
        offsets = [text(o) for o in walk(cd, "offsetVector")]
        out.append(
            {
                "id": text(cd, "CoverageId") or attr(cd, "id"),
                "srs": attr(env, "srsName") if env is not None else "",
                "axis_labels": (attr(env, "axisLabels") if env is not None else "").split(),
                "lower": text(env, "lowerCorner") if env is not None else "",
                "upper": text(env, "upperCorner") if env is not None else "",
                "grid_low": text(grid_env, "low") if grid_env is not None else "",
                "grid_high": text(grid_env, "high") if grid_env is not None else "",
                "offsets": offsets,
                "fields": [attr(f, "name") for f in walk(cd, "field")],
                "native_format": text(next(walk(cd, "nativeFormat"), None)),
            }
        )
    return out


def number_returned(data: bytes) -> int | None:
    """numberReturned / numberOfFeatures di una risposta GetFeature GML (None se assente)."""
    head = data[:4096].decode("utf-8", "replace")
    for key in ("numberReturned", "numberOfFeatures"):
        i = head.find(key + '="')
        if i >= 0:
            j = head.find('"', i + len(key) + 2)
            val = head[i + len(key) + 2 : j]
            if val.isdigit():
                return int(val)
    return None
