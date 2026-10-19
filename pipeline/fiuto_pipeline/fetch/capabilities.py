"""Comando `capabilities`: cosa offre davvero un servizio WMS/WFS/WCS.

È lo strumento della Fase 0 per riempire i [da verificare] di sources.toml:
nomi dei layer, delle coverage, degli attributi. Le risposte XML vengono
salvate in data/raw/<sorgente>/ per poterle rileggere con calma.
"""

from __future__ import annotations

from pathlib import Path

from ..config import Source
from ..errors import ConfigError, FiutoError
from . import ows
from .http import get, session

SERVICES = ("wms", "wfs", "wcs")
MAX_DESCRIBE = 15  # oltre, serve --layer per non tempestare il server


def _save(src: Source, name: str, content: bytes) -> Path:
    src.cache_dir.mkdir(parents=True, exist_ok=True)
    p = src.cache_dir / name
    p.write_bytes(content)
    return p


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)


def print_wms(caps: dict, out) -> None:
    print(f"WMS {caps['version']} - {caps['title']}", file=out)
    print(f"Formati GetMap: {', '.join(caps['formats']) or '-'}", file=out)
    print("Layer (nome | titolo | EPSG:5659 dichiarato):", file=out)
    for lyr in caps["layers"]:
        has = "si" if any("5659" in c for c in lyr["crs"]) else "no"
        name = lyr["name"] or "(gruppo senza nome)"
        print(f"  {'  ' * lyr['depth']}{name} | {lyr['title']} | {has}", file=out)
    print(
        "Nota: il WMS dà solo immagini. Per il calcolo servono un WFS/WCS o un file scaricabile;\n"
        "      i nomi dei layer qui sopra aiutano a riconoscere lo stesso dato altrove.",
        file=out,
    )


def print_wfs(caps: dict, schemas: dict, out) -> None:
    print(f"WFS {caps['version']} - {caps['title']}", file=out)
    paging = {True: "si", False: "no", None: "non dichiarato"}[caps["paging"]]
    print(f"Paginazione (ImplementsResultPaging): {paging}", file=out)
    print(f"Formati di output GetFeature: {', '.join(caps['output_formats']) or '-'}", file=out)
    print("Feature type (nome | titolo | CRS di default):", file=out)
    for ft in caps["feature_types"]:
        print(f"  {ft['name']} | {ft['title']} | {ft['default_crs']}", file=out)
        for attr, typ in schemas.get(ft["name"], []):
            print(f"      - {attr}: {typ}", file=out)
    print(
        "-> in sources.toml: service.wfs_typename = nome scelto; attributes.* = nomi degli attributi.",
        file=out,
    )


def print_wcs(caps: dict, descs: list[dict], out) -> None:
    print(f"WCS {caps['version']} - {caps['title']}", file=out)
    print(f"Formati: {', '.join(caps['formats']) or '-'}", file=out)
    print("Coverage:", file=out)
    for c in caps["coverages"]:
        print(f"  {c['id']} | {c['title']}", file=out)
    for d in descs:
        print(f"  DescribeCoverage {d['id']}:", file=out)
        print(f"      srsName: {d['srs']}", file=out)
        print(f"      assi: {' '.join(d['axis_labels']) or '-'}", file=out)
        print(f"      estensione: {d['lower']} -> {d['upper']}", file=out)
        print(
            f"      griglia: {d['grid_low']} -> {d['grid_high']}; passi: {'; '.join(d['offsets'])}", file=out
        )
        print(
            f"      bande: {', '.join(d['fields']) or '-'}; formato nativo: {d['native_format'] or '-'}",
            file=out,
        )
    print(
        "-> in sources.toml: service.wcs_coverage_id, wcs_axis_x / wcs_axis_y (dagli assi),\n"
        "   wcs_format (uno dei formati sopra, GeoTIFF se c'è). Il CRS della coverage deve\n"
        "   coincidere con `crs` della sorgente (atteso EPSG:5659, da confermare con srsName).",
        file=out,
    )


def run_capabilities(
    src: Source,
    *,
    service: str | None = None,
    url: str | None = None,
    layer: str | None = None,
    out=None,
) -> dict:
    """Interroga i servizi della sorgente e stampa cosa offrono. Ritorna i dati letti."""
    import sys

    out = out or sys.stdout
    if url and not service:
        raise ConfigError("con --url serve anche --service (wms, wfs o wcs)")
    targets: list[tuple[str, str]] = []
    if url:
        targets.append((service.lower(), url))
    else:
        for svc in SERVICES if not service else (service.lower(),):
            ep = src.endpoint(svc)
            if ep:
                targets.append((svc, ep))
    if not targets:
        known = ", ".join(f"{k}={v}" for k, v in src.endpoints.items() if v) or "nessuno"
        raise ConfigError(
            f"[{src.id}] nessun endpoint WMS/WFS/WCS in sources.toml (endpoint noti: {known}).\n"
            f"Se trovi l'URL del servizio (es. nei metadati del geoportale), provalo con\n"
            f"  python -m fiuto_pipeline capabilities {src.id} --service wfs --url <URL>\n"
            f"e poi scrivilo in [sources.{src.id}.endpoints]."
        )

    sess = session()
    result = {}
    for svc, base in targets:
        req = ows.build_url(base, ows.capabilities_params(svc))
        print(f"\n== {src.id}: {svc.upper()} {base}\nGetCapabilities: {req}", file=out)
        try:
            resp = get(sess, base, params=ows.capabilities_params(svc))
            saved = _save(src, f"capabilities_{svc}.xml", resp.content)
            print(f"XML salvato in {saved}", file=out)
            if svc == "wms":
                caps = ows.parse_wms_capabilities(resp.content)
                print_wms(caps, out)
            elif svc == "wfs":
                caps = ows.parse_wfs_capabilities(resp.content)
                names = [ft["name"] for ft in caps["feature_types"]]
                if layer:
                    names = [n for n in names if n == layer] or [layer]
                schemas = {}
                if len(names) > MAX_DESCRIBE:
                    print(
                        f"{len(names)} feature type: per gli attributi rilancia con --layer <nome>", file=out
                    )
                else:
                    version = caps["version"] or "2.0.0"
                    for n in names:
                        params = ows.describe_feature_type_params(n, version)
                        r = get(sess, base, params=params)
                        _save(src, f"describe_{_safe(n)}.xsd", r.content)
                        try:
                            schemas.update(ows.parse_describe_feature_type(r.content))
                        except ValueError as exc:
                            print(f"  DescribeFeatureType {n}: {exc}", file=out)
                        # alcuni server rispondono con il nome senza prefisso
                        if n not in schemas and n.split(":")[-1] in schemas:
                            schemas[n] = schemas[n.split(":")[-1]]
                print_wfs(caps, schemas, out)
                caps["schemas"] = schemas
            else:
                caps = ows.parse_wcs_capabilities(resp.content)
                ids = [c["id"] for c in caps["coverages"]]
                if layer:
                    ids = [layer]
                descs = []
                if len(ids) > MAX_DESCRIBE:
                    print(f"{len(ids)} coverage: per i dettagli rilancia con --layer <coverage id>", file=out)
                else:
                    for cid in ids:
                        r = get(sess, base, params=ows.describe_coverage_params(cid))
                        _save(src, f"describe_{_safe(cid)}.xml", r.content)
                        try:
                            descs += ows.parse_describe_coverage(r.content)
                        except ValueError as exc:
                            print(f"  DescribeCoverage {cid}: {exc}", file=out)
                print_wcs(caps, descs, out)
                caps["descriptions"] = descs
            result[svc] = caps
        except (FiutoError, ValueError) as exc:
            print(f"ERRORE {svc.upper()}: {exc}", file=out)
            result[svc] = {"error": str(exc)}
    return result
