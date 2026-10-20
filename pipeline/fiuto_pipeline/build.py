"""Build completo per un'AOI: derive -> score -> GeoTIFF/report -> PMTiles.

I parametri la cui sorgente non è configurata si saltano (e si dice perché).
Una sorgente configurata male invece ferma tutto: meglio che un numero falso.
"""

from __future__ import annotations

import json
from datetime import datetime, UTC
from pathlib import Path

import numpy as np

from . import __version__
from .config import STATUS_OK, Source, get_source, load_aois, load_build_config, load_sources
from .derive import (
    derive_bedrock,
    derive_caco3,
    derive_elevation,
    derive_forest,
    derive_forest_mask,
    derive_ph,
    derive_texture,
)
from .errors import ConfigError, FiutoError, NotConfigured
from .export import export_vth
from .grid import Grid, resolve_aoi
from .model import NA, load_model
from .paths import BUILD_DIR
from .score import build_report, combine, write_score_geotiff, write_unmapped_csv

# parametro -> sorgenti candidate, in ordine di preferenza
PARAM_SOURCES = {
    "bedrock": ["geologia"],
    "ph": ["ph", "suoli"],  # raster regionale del pH se c'è, altrimenti profili della carta dei suoli
    "caco3": ["suoli"],
    "texture": ["suoli"],
    "elevation": ["dtm", "dem10"],
    "forest_type": ["forestale"],
    "hosts": ["forestale"],
}


# Licenze riconosciute nel campo license di sources.toml (deve iniziare così).
KNOWN_LICENCES = ("CC BY 4.0", "CC BY 3.0")


def licence_short(text: str) -> str:
    t = (text or "").strip()
    for lic in KNOWN_LICENCES:
        if t.startswith(lic):
            return lic
    return "licenza da verificare"


def attribution(srcs: list, credit: str = "Elaborazione fiuto (VTH).") -> str:
    """Attribuzione per il metadata dei tile: la CC BY chiede di citare fonte e licenza.

    L'app la mostra nell'angolo della mappa, quindi resta corta: titoli abbreviati
    e raggruppati per licenza. I titoli completi sono in metadata["sources"].
    """
    by_lic: dict[str, list[str]] = {}
    for s in srcs:
        short = (s.title or s.id).split(" - ")[0].split(" (")[0]
        titles = by_lic.setdefault(licence_short(s.license), [])
        if short not in titles:
            titles.append(short)
    parts = [f"{lic}: {', '.join(titles)}" for lic, titles in by_lic.items()]
    return "Dati © Regione Emilia-Romagna, " + "; ".join(parts) + ". " + credit


def _derive_one(pid: str, src: Source, grid: Grid, model, mask, lookup_dir):
    if pid == "elevation":
        return derive_elevation(src, grid, model)
    if pid == "ph":
        return derive_ph(src, grid, model)
    if pid == "caco3":
        return derive_caco3(src, grid, model)
    if pid == "texture":
        return derive_texture(src, grid, model, mask=mask, lookup_dir=lookup_dir)
    if pid == "bedrock":
        return derive_bedrock(src, grid, model, mask=mask, lookup_dir=lookup_dir)
    raise ValueError(pid)


def run_build(
    aoi_name: str,
    *,
    sources_path: Path | None = None,
    aoi_path: Path | None = None,
    build_path: Path | None = None,
    lookup_dir: Path | None = None,
    out_dir: Path | None = None,
    forest_mask: bool = True,
    tiles: bool = True,
    raw_dir: Path | None = None,
    log=print,
) -> dict:
    cfg = load_build_config(build_path)
    model = load_model(cfg.model_path)
    sources = load_sources(sources_path, raw_dir=raw_dir)
    aois = load_aois(aoi_path)
    if aoi_name not in aois:
        raise ConfigError(f"AOI '{aoi_name}' non trovata in aoi.toml (disponibili: {', '.join(aois)})")
    aoi = resolve_aoi(aois[aoi_name], cfg.crs)
    grid = Grid.from_bounds(aoi.bounds, cfg.crs, cfg.cell_size)
    built = datetime.now(UTC).isoformat(timespec="seconds")
    out_dir = Path(out_dir) if out_dir else BUILD_DIR / aoi_name

    log(
        f"Modello {model.id}, AOI {aoi_name}: griglia {grid.width}x{grid.height} celle da {grid.cell_size:g} m ({grid.crs})"
    )
    if aoi.approximate:
        log(f"ATTENZIONE: AOI approssimativa ({aoi.description or 'bbox scritto a mano'})")
    aoi_mask = aoi.mask(grid)

    params: dict[str, np.ndarray] = {}
    status: dict[str, dict] = {}
    unmapped: dict[str, list] = {}
    used: dict[str, set] = {}

    lookups_used: dict[str, str] = {}  # param -> tabella
    drafts: dict[str, int] = {}  # tabella -> righe BOZZA

    remote = set(model.remote_params())

    def ok(res):
        if res.param not in remote:
            # es. ospiti in vth-v2: il derive li calcola ancora, ma il modello non li usa da remoto
            log(f"  - {res.param}: non è un parametro remoto di {model.id}, ignorato")
            return
        if res.unmapped:
            unmapped[res.param] = res.unmapped
        if res.lookup:
            lookups_used[res.param] = res.lookup
        if not (res.array != NA).any():
            status[res.param] = {"status": "nessun valore", "source": res.source, "detail": res.detail}
            log(
                f"  - {res.param}: nessuna cella classificata ({res.detail})"
                + (f"; {len(res.unmapped)} valori da classificare" if res.unmapped else "")
            )
            return
        params[res.param] = res.array
        status[res.param] = {"status": "ok", "source": res.source, "detail": res.detail}
        if res.lookup:
            status[res.param]["lookup"] = res.lookup
            if res.drafts:
                drafts[res.lookup] = res.drafts
                status[res.param]["lookup_bozza"] = res.drafts
        used.setdefault(res.source, set()).add(res.param)
        log(
            f"  + {res.param}: da {res.source}"
            + (f" ({len(res.unmapped)} valori non classificati)" if res.unmapped else "")
        )

    def skip(pid, reason):
        if pid not in remote:
            return
        status[pid] = {"status": "saltato", "reason": reason}
        log(f"  - {pid}: saltato. {reason}")

    # 1. maschera bosco (e intanto tipo di bosco e ospiti)
    log("Maschera bosco:")
    fsrc = sources.get("forestale")
    mask_info: dict
    try:
        if fsrc is None:
            raise NotConfigured("sorgente 'forestale' assente da sources.toml")
        fmask, detail = derive_forest_mask(fsrc, grid)
        mask = fmask & aoi_mask
        mask_info = {"type": "bosco", "source": "forestale", "detail": detail}
        used.setdefault("forestale", set()).add("mask")
        log(f"  + bosco da forestale: {int(mask.sum())} celle ({mask.sum() * grid.cell_area_ha:.0f} ha)")
    except NotConfigured as exc:
        if forest_mask:
            raise FiutoError(
                f"Senza carta forestale non c'è maschera bosco e lo score vale solo in bosco (BRIEF §4.3).\n"
                f"{exc}\nConfigura [sources.forestale] oppure, solo per prova, usa --no-forest-mask."
            ) from None
        mask = aoi_mask.copy()
        mask_info = {
            "type": "nessuna",
            "reason": str(exc),
            "note": "build di prova: score anche fuori dal bosco",
        }
        log(f"  ! nessuna maschera bosco (--no-forest-mask): {exc}")
    if not mask.any():
        log("  ! maschera vuota: nessuna cella da calcolare nell'AOI")

    log("Parametri:")
    if fsrc is not None:
        try:
            for res in derive_forest(fsrc, grid, model, mask=mask, lookup_dir=lookup_dir).values():
                ok(res)
        except NotConfigured as exc:
            skip("forest_type", str(exc))
            skip("hosts", str(exc))
    else:
        skip("forest_type", "sorgente 'forestale' assente")
        skip("hosts", "sorgente 'forestale' assente")

    # 2. gli altri parametri, nell'ordine del modello
    for pid in model.remote_params():
        if pid in ("forest_type", "hosts"):
            continue
        reasons = []
        for sid in PARAM_SOURCES.get(pid, []):
            src = sources.get(sid)
            if src is None:
                reasons.append(f"sorgente '{sid}' assente da sources.toml")
                continue
            try:
                ok(_derive_one(pid, src, grid, model, mask, lookup_dir))
                break
            except NotConfigured as exc:
                reasons.append(str(exc))
        else:
            skip(pid, " | ".join(reasons) or "nessuna sorgente prevista")

    # 3. valori da classificare (anche se poi ci si ferma: servono per riempire le tabelle)
    outputs: dict = {}
    if unmapped:
        out_dir.mkdir(parents=True, exist_ok=True)
    for pid, rows in unmapped.items():
        p = write_unmapped_csv(out_dir / f"da_classificare_{pid}.csv", pid, rows, lookups_used.get(pid, ""))
        if p:
            outputs[f"da_classificare_{pid}"] = str(p)
            log(f"Da classificare per {pid}: {len(rows)} valori -> {p}")

    # 4. score
    if not params:
        where = f" Valori da classificare in {out_dir}." if outputs else ""
        raise FiutoError(
            "nessun parametro disponibile: niente da calcolare."
            f"{where} `python -m fiuto_pipeline info` dice cosa manca."
        )
    result = combine(params, model, mask)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"vth_{aoi_name}"
    sources_meta = [
        {
            "id": sid,
            "status": get_source(sources, sid).status,
            "verified": get_source(sources, sid).status == STATUS_OK,
            "params": sorted(ps),
        }
        for sid, ps in sorted(used.items())
    ]
    tif = write_score_geotiff(
        out_dir / f"{stem}.tif",
        grid,
        result,
        params,
        model,
        tags={
            "model": model.id,
            "built": built,
            "aoi": aoi_name,
            "generator": f"fiuto_pipeline {__version__}",
        },
    )
    outputs["geotiff"] = str(tif)

    # 5. tile
    if tiles:
        metadata = {
            "model": model.id,
            "built": built,
            "aoi": aoi_name,
            "sources": sources_meta,
            "mask": mask_info["type"],
            "cell_size_m": grid.cell_size,
            "generator": f"fiuto_pipeline {__version__}",
        }
        metadata["attribution"] = attribution([get_source(sources, sid) for sid in sorted(used)])
        if aoi.approximate:
            metadata["aoi_note"] = "AOI approssimativa: " + (aoi.description or "bbox scritto a mano")
        warnings_meta = []
        if mask_info["type"] != "bosco":
            warnings_meta.append("build di prova senza maschera bosco")
        if drafts:
            warnings_meta.append(
                "tabelle di lookup in BOZZA, da rivedere: "
                + ", ".join(f"{t} ({n} righe)" for t, n in sorted(drafts.items()))
            )
        if warnings_meta:
            metadata["warning"] = "; ".join(warnings_meta)
        exp = export_vth(
            params,
            mask,
            grid,
            model,
            out_dir,
            stem=stem,
            minzoom=cfg.minzoom,
            maxzoom=cfg.maxzoom,
            name=f"fiuto {model.id} {aoi_name}",
            description=f"Score remoto {model.id} ({aoi_name}, celle {grid.cell_size:g} m). Stima: VTH è un prior, non la verità.",
            metadata=metadata,
            simplification=cfg.simplification,
            simplification_max_zoom=cfg.simplification_max_zoom,
            verify_max_tiles=cfg.verify_max_tiles,
        )
        outputs["export"] = exp
        if exp.get("hint"):
            log(exp["hint"])

    report = build_report(
        model=model,
        built=built,
        aoi={
            "name": aoi_name,
            "description": aoi.description,
            "approximate": aoi.approximate,
            "bounds": list(aoi.bounds),
        },
        grid={
            "crs": grid.crs,
            "cell_size": grid.cell_size,
            "width": grid.width,
            "height": grid.height,
            "bounds": list(grid.bounds),
        },
        mask_info=mask_info,
        params_status=status,
        params=params,
        result=result,
        sources=[
            {
                **s,
                "license": get_source(sources, s["id"]).license,
                "data": status_detail(get_source(sources, s["id"])),
            }
            for s in sources_meta
        ],
        outputs=outputs,
        cell_ha=grid.cell_area_ha,
    )
    report["unmapped"] = unmapped
    report["lookup_bozza"] = drafts
    rpath = out_dir / "report.json"
    rpath.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    log(
        f"Score: {report['score']['cells_score']} celle con score su {report['score']['cells_mask']} in maschera"
    )
    log(f"Disponibilità parametri (% celle in maschera): {report['availability_pct']}")
    for pid, rows in unmapped.items():
        top = ", ".join(f"{r['value']} ({r.get('ha_bosco', r['ha'])} ha)" for r in rows[:5])
        log(f"  {pid}, i più estesi in maschera: {top}")
    log(f"Report: {rpath}")
    for k, v in outputs.items():
        if isinstance(v, str):
            log(f"  {k}: {v}")
    if tiles and outputs["export"]["tiles"]["path"]:
        log(
            f"  pmtiles: {outputs['export']['tiles']['path']} ({outputs['export']['tiles']['method']}, GDAL {outputs['export']['tiles']['gdal']})"
        )
    return report


def status_detail(src: Source) -> str:
    try:
        return str(src.data_path())
    except (NotConfigured, ConfigError) as exc:
        return f"non disponibile: {exc}"
