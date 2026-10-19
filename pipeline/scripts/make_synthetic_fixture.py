"""Fixture SINTETICA per i test e2e dell'app: un piccolo PMTiles `vth` finto.

DATI SINTETICI DI TEST, NON REALI. I valori dei parametri sono blocchi
disegnati a mano per coprire i casi del contratto `tiles` (chiavi omesse,
score assente sotto minParams, ospiti 0/1, aree fuori bosco senza feature).
L'area (lon 10.0-10.1, lat 44.6-44.7) serve solo a posizionare la mappa.

Passa per lo stesso codice di export del build (polygonize -> PMTiles ->
verifica del contratto). Uso, da pipeline/:

    .venv/bin/python scripts/make_synthetic_fixture.py [--out PERCORSO]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fiuto_pipeline import __version__  # noqa: E402
from fiuto_pipeline.export import export_vth  # noqa: E402
from fiuto_pipeline.grid import Grid  # noqa: E402
from fiuto_pipeline.model import NA, load_model  # noqa: E402
from fiuto_pipeline.paths import REPO_ROOT  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "app" / "e2e" / "fixtures" / "synthetic-vth.pmtiles"
BBOX_WGS84 = (10.0, 44.6, 10.1, 44.7)
# Data fissa: il file resta identico a ogni rigenerazione (comodo in git).
BUILT = "2026-10-19T00:00:00+00:00"


def synthetic_params(shape: tuple[int, int]) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Blocchi 3x3 di valori finti + maschera bosco finta."""
    h, w = shape
    r = [0, h // 3, 2 * h // 3, h]
    c = [0, w // 3, 2 * w // 3, w]

    def blocks(table):
        a = np.full(shape, NA, dtype="uint8")
        for i in range(3):
            for j in range(3):
                a[r[i] : r[i + 1], c[j] : c[j + 1]] = table[i][j]
        return a

    N = NA
    params = {
        "bedrock": blocks([[3, 2, N], [3, 1, 0], [N, N, N]]),
        "ph": blocks([[3, 1, 2], [2, 3, 0], [N, N, 1]]),
        "caco3": blocks([[2, N, N], [3, N, N], [N, N, N]]),
        "texture": blocks([[3, 3, 1], [2, 3, 3], [N, 0, N]]),
        "elevation": blocks([[3, 3, 3], [2, 2, 2], [1, 1, 0]]),
        "forest_type": blocks([[3, 2, 3], [3, 1, 0], [N, 2, N]]),
        "hosts": blocks([[1, 1, 0], [1, 0, 0], [N, 1, N]]),
    }
    # Riga in basso a sinistra: solo 1 parametro (elevation) -> niente score.
    # Riga in basso al centro: 4 parametri -> score presente.
    # Riga in basso a destra: 2 parametri (ph, elevation) -> niente score.
    mask = np.ones(shape, dtype=bool)
    mask[h // 2 - 4 : h // 2 + 4, :] = False  # "strada" non boscata
    mask[: h // 6, 5 * w // 6 :] = False  # "prato" in alto a destra
    return params, mask


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Genera la fixture PMTiles SINTETICA per l'app.")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"default: {DEFAULT_OUT}")
    args = ap.parse_args(argv)

    model = load_model()
    from pyproj import Transformer

    t = Transformer.from_crs("EPSG:4326", "EPSG:5659", always_xy=True)
    grid = Grid.from_bounds(t.transform_bounds(*BBOX_WGS84, densify_pts=21), "EPSG:5659", 25.0)
    params, mask = synthetic_params(grid.shape)

    out = args.out
    stem = out.name.removesuffix(".pmtiles")
    res = export_vth(
        params,
        mask,
        grid,
        model,
        out.parent,
        stem=stem,
        minzoom=8,
        maxzoom=14,
        name="fiuto SYNTHETIC test fixture",
        description="DATI SINTETICI DI TEST, non reali: generati da pipeline/scripts/make_synthetic_fixture.py. Non usare sul campo.",
        metadata={
            "model": model.id,
            "built": BUILT,
            "aoi": "synthetic-test",
            "sources": [
                {"id": "synthetic", "status": "sintetico", "verified": False, "params": model.remote_params()}
            ],
            "synthetic": True,
            "mask": "sintetica",
            "cell_size_m": grid.cell_size,
            "generator": f"fiuto_pipeline {__version__} scripts/make_synthetic_fixture.py",
        },
        simplification=1.0,
        geojsonseq=False,
        verify_max_tiles=None,
    )
    v = res["verify"]
    print(
        f"Fixture SINTETICA scritta: {res['tiles']['path']} ({v['bytes']} byte, {res['features']} poligoni)"
    )
    print(
        f"  metodo {res['tiles']['method']} (GDAL {res['tiles']['gdal']}), zoom {v['min_zoom']}-{v['max_zoom']}"
    )
    print(f"  tile verificati: {v['tiles_checked']}, feature senza score: {v['features_without_score']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
