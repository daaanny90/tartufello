"""Verifica di un PMTiles rispetto al contratto `tiles` del modello.

Si rilegge il file due volte: con GDAL (pyogrio) per essere sicuri che sia
leggibile, e tile per tile con il decoder MVT per controllare le proprietà
così come le vedrà l'app (chiavi omesse quando il parametro manca).
"""

from __future__ import annotations

from pathlib import Path

import pyogrio

from ..errors import FiutoError
from ..model import Model
from .mvt import decode_tile

REQUIRED_METADATA = ("model", "built", "aoi", "sources")


def _check_feature(props: dict, model: Model, allowed: set[str], where: str) -> list[str]:
    errs = []
    extra = set(props) - allowed
    if extra:
        errs.append(f"{where}: chiavi fuori contratto {sorted(extra)}")
    for k in ("pts", "max", "n"):
        if not isinstance(props.get(k), int):
            errs.append(f"{where}: '{k}' mancante o non intero ({props.get(k)!r})")
    if errs:
        return errs
    present = [p for p in model.remote_params() if p in props]
    for p in present:
        v = props[p]
        if not isinstance(v, int) or not 0 <= v <= model.remote_max(p):
            errs.append(f"{where}: {p}={v!r} fuori da 0..{model.remote_max(p)}")
    if props["n"] != len(present):
        errs.append(f"{where}: n={props['n']} ma parametri presenti {len(present)}")
    if props["pts"] != sum(props[p] for p in present):
        errs.append(f"{where}: pts={props['pts']} diverso dalla somma dei parametri")
    if props["max"] != sum(model.remote_max(p) for p in present):
        errs.append(f"{where}: max={props['max']} diverso dalla somma dei massimi remoti")
    should_score = props["n"] >= model.min_params and props["max"] > 0
    if "score" in props:
        s = props["score"]
        if not should_score:
            errs.append(f"{where}: score presente con n={props['n']} < minParams")
        # GDAL scrive 0.0 e 1.0 come interi MVT: per l'app è lo stesso numero.
        elif isinstance(s, bool) or not isinstance(s, (int, float)) or not 0 <= s <= 1 or round(s, 3) != s:
            errs.append(f"{where}: score={s!r} non è un numero 0..1 a 3 decimali")
        elif abs(s - props["pts"] / props["max"]) > 0.0005 + 1e-9:
            errs.append(f"{where}: score={s} diverso da pts/max")
    elif should_score:
        errs.append(f"{where}: score assente con n={props['n']} >= minParams")
    return errs


def verify_pmtiles(
    path: Path, model: Model, *, max_tiles: int | None = None, require_metadata: bool = True
) -> dict:
    """Controlla header, metadata e (un campione di) tile. Errore se qualcosa non torna."""
    from pmtiles.reader import MmapSource, Reader, all_tiles
    from pmtiles.tile import TileType

    path = Path(path)
    layer = model.tile_layer
    errors: list[str] = []

    # 1. GDAL deve riuscire a leggerlo
    try:
        layers = [str(r[0]) for r in pyogrio.list_layers(path)]
        gdal_info = pyogrio.read_info(path, layer=layer) if layer in layers else None
    except Exception as exc:  # noqa: BLE001
        raise FiutoError(f"{path}: GDAL non riesce a leggerlo ({exc})") from exc
    if layers != [layer]:
        errors.append(f"layer GDAL {layers}, atteso ['{layer}']")

    # 2. header e metadata
    with open(path, "rb") as f:
        src = MmapSource(f)
        reader = Reader(src)
        header = reader.header()
        meta = reader.metadata()
        if header["tile_type"] != TileType.MVT:
            errors.append(f"tile_type {header['tile_type']}, atteso MVT")
        if require_metadata:
            for k in REQUIRED_METADATA:
                if k not in meta:
                    errors.append(f"metadata senza '{k}'")
            if meta.get("model") not in (None, model.id):
                errors.append(f"metadata model={meta.get('model')}, atteso {model.id}")
        vl = [v.get("id") for v in meta.get("vector_layers", [])]
        if vl != [layer]:
            errors.append(f"vector_layers {vl}, atteso ['{layer}']")

        # 3. tile: tutti o un campione regolare
        total = header["addressed_tiles_count"]
        step = 1 if not max_tiles or total <= max_tiles else max(1, total // max_tiles)
        allowed = set(model.tile_properties)
        n_tiles = n_feat = n_noscore = 0
        zooms = set()
        for i, ((z, x, y), data) in enumerate(all_tiles(src)):
            if i % step:
                continue
            n_tiles += 1
            zooms.add(z)
            for lyr in decode_tile(data):
                if lyr["name"] != layer:
                    errors.append(f"tile {z}/{x}/{y}: layer '{lyr['name']}'")
                    continue
                for feat in lyr["features"]:
                    n_feat += 1
                    if "score" not in feat["properties"]:
                        n_noscore += 1
                    errors.extend(_check_feature(feat["properties"], model, allowed, f"tile {z}/{x}/{y}"))
            if len(errors) > 20:
                break

    if errors:
        raise FiutoError(f"{path}: PMTiles non conforme al contratto:\n  - " + "\n  - ".join(errors[:20]))
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "tiles_total": total,
        "tiles_checked": n_tiles,
        "features_checked": n_feat,
        "features_without_score": n_noscore,
        "zooms": sorted(zooms),
        "min_zoom": header["min_zoom"],
        "max_zoom": header["max_zoom"],
        "gdal_features": gdal_info["features"] if gdal_info else None,
        "metadata_keys": sorted(meta),
    }
