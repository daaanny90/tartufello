"""Comando `info`: cosa è configurato e cosa è ancora [da verificare]."""

from __future__ import annotations

import sys

from .config import STATUS_OK, Source, load_aois, load_build_config, load_sources
from .errors import ConfigError, FiutoError, NotConfigured
from .lookups import SPECS, load_lookup
from .model import load_model

# sorgente -> {uso nel build: attributi necessari}
DERIVE_NEEDS = {
    "dtm": {"elevation": []},
    "dem10": {"elevation": []},
    "ph": {"ph": []},  # ph_attr serve solo se il dato è vettoriale
    "suoli": {"texture": ["texture_attr"], "caco3": ["caco3_attr"]},
    "geologia": {"bedrock": ["unit_code_attr"]},
    "forestale": {"maschera bosco": [], "forest_type": ["forest_type_attr"], "hosts": ["forest_type_attr"]},
}
# parametro -> (tabella, colonna da compilare)
LOOKUP_NEEDS = {
    "texture": ("suoli_tessitura", "texture_id"),
    "bedrock": ("geologia_vth", "vth_class"),
    "forest_type": ("forestale_vth", "forest_class"),
    "hosts": ("forestale_vth", "hosts"),
}
FETCH_NEEDS = {
    "url": ("endpoints", ["download"]),
    "wfs": ("endpoints", ["wfs"], "service", ["wfs_typename"]),
    "wcs": ("endpoints", ["wcs"], "service", ["wcs_coverage_id", "wcs_axis_x", "wcs_axis_y", "wcs_format"]),
}


def _fetch_state(src: Source) -> str:
    parts = []
    for method, spec in FETCH_NEEDS.items():
        # mostra solo i metodi che la sorgente prevede (chiave presente nel TOML)
        if spec[1][0] not in src.endpoints:
            continue
        miss = src.missing(spec[0], *spec[1])
        if len(spec) > 2:
            miss += src.missing(spec[2], *spec[3])
        if not miss:
            return f"pronto ({method})"
        parts.append(f"{method}: mancano {', '.join(miss)}")
    return "; ".join(parts) if parts else "nessun metodo automatico: scarico a mano + local_path"


def _data_state(src: Source) -> str:
    try:
        return f"{src.data_path()}"
    except NotConfigured:
        return "nessuno (local_path vuoto, niente in cache)"
    except ConfigError as exc:
        return f"ERRORE: {exc}"


def run_info(sources_path=None, aoi_path=None, build_path=None, lookup_dir=None, out=None) -> int:
    out = out or sys.stdout
    todo = 0
    try:
        cfg = load_build_config(build_path)
        model = load_model(cfg.model_path)
        print(f"Modello: {model.id} ({model.path})", file=out)
        print(
            f"  parametri remoti: {', '.join(model.remote_params())}; minParams {model.min_params}", file=out
        )
        print(f"  griglia {cfg.crs}, celle {cfg.cell_size:g} m; tile z{cfg.minzoom}-{cfg.maxzoom}", file=out)
    except FiutoError as exc:
        print(f"Modello/build.toml: ERRORE {exc}", file=out)
        return 1

    sources = load_sources(sources_path)
    print("\nSorgenti (sources.toml):", file=out)
    for sid, src in sources.items():
        flag = "ok" if src.status == STATUS_OK else src.status
        if src.status != STATUS_OK:
            todo += 1
        print(
            f"  {sid} [{flag}] {src.title}" + (f" - {src.status_note}" if src.status_note else ""), file=out
        )
        if src.params:
            print(f"      per: {', '.join(src.params)}", file=out)
        print(f"      licenza: {src.license or '[da verificare]'}", file=out)
        eps = [k for k, v in src.endpoints.items() if v]
        print(f"      endpoint: {', '.join(eps) or 'nessuno'}", file=out)
        print(f"      dati locali: {_data_state(src)}", file=out)
        print(f"      scarico: {_fetch_state(src)}", file=out)
        for use, keys in DERIVE_NEEDS.get(sid, {}).items():
            miss = src.missing("attributes", *keys)
            print(f"      {use}: {'attributi ok' if not miss else 'mancano ' + ', '.join(miss)}", file=out)
        if any(src.endpoint(s) for s in ("wms", "wfs", "wcs")) and src.status != STATUS_OK:
            print(f"      -> python -m fiuto_pipeline capabilities {sid}", file=out)

    print("\nTabelle di lookup (pipeline/lookups):", file=out)
    for name in SPECS:
        try:
            lk = load_lookup(name, lookup_dir)
        except ConfigError as exc:
            print(f"  {name}.csv: ERRORE {exc}", file=out)
            todo += 1
            continue
        cols = [col for t, col in LOOKUP_NEEDS.values() if t == name]
        counts = ", ".join(f"{c}: {lk.mapped_count(c)}" for c in cols)
        empty = all(lk.mapped_count(c) == 0 for c in cols)
        if empty:
            todo += 1
        print(
            f"  {name}.csv: {len(lk.rows)} righe ({counts})" + ("  [da riempire]" if empty else ""), file=out
        )

    print("\nAOI (aoi.toml):", file=out)
    try:
        for name, a in load_aois(aoi_path).items():
            kind = f"bbox {a.crs}" if a.bbox else f"file {a.path}"
            warn = "  [APPROSSIMATIVA, da sostituire]" if a.approximate else ""
            print(f"  {name}: {kind}{warn}", file=out)
            if a.description:
                print(f"      {a.description}", file=out)
    except FiutoError as exc:
        print(f"  ERRORE {exc}", file=out)

    from .build import PARAM_SOURCES

    ready, listing = [], []
    for pid in model.remote_params():
        for sid in PARAM_SOURCES.get(pid, []):
            src = sources.get(sid)
            if src is None or not src.has_data():
                continue
            needs = DERIVE_NEEDS.get(sid, {}).get(pid, [])
            if src.missing("attributes", *needs):
                continue
            if pid in LOOKUP_NEEDS:
                t, c = LOOKUP_NEEDS[pid]
                try:
                    if load_lookup(t, lookup_dir).mapped_count(c) == 0:
                        listing.append(pid)
                        break
                except ConfigError:
                    break
            ready.append(pid)
            break
    print(f"\nParametri pronti per il build: {', '.join(ready) or 'nessuno'}", file=out)
    if listing:
        print(
            f"Dati ok ma tabella vuota (il build elenca i valori da classificare): {', '.join(listing)}",
            file=out,
        )
    print(f"Voci ancora da verificare/riempire: {todo}", file=out)
    return 0
