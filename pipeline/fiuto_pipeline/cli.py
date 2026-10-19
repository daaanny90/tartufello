"""Riga di comando: python -m fiuto_pipeline <comando>."""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

from .errors import FiutoError, NotConfigured


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m fiuto_pipeline",
        description="Pipeline di fiuto: dati regionali ER -> score remoto VTH -> PMTiles.",
    )
    p.add_argument("--sources", type=Path, help="sources.toml alternativo (default: pipeline/sources.toml)")
    p.add_argument("--aoi-file", type=Path, help="aoi.toml alternativo (default: pipeline/aoi.toml)")
    p.add_argument("--build-config", type=Path, help="build.toml alternativo (default: pipeline/build.toml)")
    p.add_argument(
        "--lookups", type=Path, help="cartella delle tabelle di lookup (default: pipeline/lookups)"
    )
    sub = p.add_subparsers(dest="cmd", required=True, metavar="comando")

    sub.add_parser("info", help="stato di sorgenti, lookup e AOI: cosa è ancora [da verificare]")

    c = sub.add_parser("capabilities", help="GetCapabilities (e Describe*) dei servizi di una sorgente")
    c.add_argument("source", help="id della sorgente in sources.toml (es. suoli, geologia, dtm)")
    c.add_argument("--service", choices=["wms", "wfs", "wcs"], help="solo questo servizio")
    c.add_argument("--url", help="prova un endpoint non ancora in sources.toml (serve --service)")
    c.add_argument("--layer", help="feature type o coverage da descrivere (se sono tanti)")

    f = sub.add_parser("fetch", help="scarica una sorgente nella cache locale (data/raw/)")
    f.add_argument("source", help="id della sorgente in sources.toml")
    f.add_argument("--aoi", help="area da scaricare (obbligatoria per WFS e WCS)")
    f.add_argument("--method", choices=["url", "wfs", "wcs"], help="forza il metodo di scarico")
    f.add_argument("--force", action="store_true", help="riscarica anche se è già in cache")

    b = sub.add_parser("build", help="derive + score + export per un'AOI")
    b.add_argument("--aoi", required=True, help="nome dell'AOI in aoi.toml")
    b.add_argument("--out", type=Path, help="cartella di output (default: data/build/<aoi>/)")
    b.add_argument(
        "--no-forest-mask",
        action="store_true",
        help="solo per prova: calcola anche senza carta forestale (il modello vale solo in bosco)",
    )
    b.add_argument("--no-tiles", action="store_true", help="salta poligoni e PMTiles (solo GeoTIFF e report)")
    return p


def _cmd_capabilities(args) -> int:
    from .config import get_source, load_sources
    from .fetch import run_capabilities

    src = get_source(load_sources(args.sources), args.source)
    res = run_capabilities(src, service=args.service, url=args.url, layer=args.layer)
    return 1 if any("error" in v for v in res.values()) else 0


def _cmd_fetch(args) -> int:
    from .config import get_source, load_aois, load_build_config, load_sources
    from .fetch import run_fetch
    from .grid import resolve_aoi

    src = get_source(load_sources(args.sources), args.source)
    bbox = None
    align = None
    if args.aoi:
        aois = load_aois(args.aoi_file)
        if args.aoi not in aois:
            raise FiutoError(f"AOI '{args.aoi}' non trovata (disponibili: {', '.join(aois)})")
        if not src.crs:
            raise FiutoError(f"[{src.id}] manca crs in sources.toml")
        cfg = load_build_config(args.build_config)
        a = resolve_aoi(aois[args.aoi], src.crs)
        m = 4 * cfg.cell_size  # margine: la media sui bordi ha bisogno di dati attorno
        bbox = (a.bounds[0] - m, a.bounds[1] - m, a.bounds[2] + m, a.bounds[3] + m)
        align = cfg.cell_size
    path = run_fetch(src, method=args.method, bbox=bbox, force=args.force, align=align)
    if path:
        print(f"Fatto: {path}\n(il build lo usa se [sources.{src.id}] local_path è vuoto)")
    return 0


def _cmd_build(args) -> int:
    from .build import run_build

    run_build(
        args.aoi,
        sources_path=args.sources,
        aoi_path=args.aoi_file,
        build_path=args.build_config,
        lookup_dir=args.lookups,
        out_dir=args.out,
        forest_mask=not args.no_forest_mask,
        tiles=not args.no_tiles,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    warnings.formatwarning = lambda msg, cat, *a, **k: f"avviso: {msg}\n"
    try:
        if args.cmd == "info":
            from .info import run_info

            return run_info(args.sources, args.aoi_file, args.build_config, args.lookups)
        if args.cmd == "capabilities":
            return _cmd_capabilities(args)
        if args.cmd == "fetch":
            return _cmd_fetch(args)
        if args.cmd == "build":
            return _cmd_build(args)
    except NotConfigured as exc:
        print(f"non configurato: {exc}", file=sys.stderr)
        return 2
    except FiutoError as exc:
        print(f"errore: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
