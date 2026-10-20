"""Basemap offline per un'AOI (comando `basemap`).

Scrive in data/build/<aoi>/:
- rilievo_<aoi>.pmtiles: ombreggiatura dal DTM 5x5 ricampionato a 10 m, tile
  WEBP (PNG se GDAL non ha WEBP), zoom 10-15, nodata trasparente;
- base_<aoi>.pmtiles: vettoriale con i layer contours, trails, roads, water,
  places (zoom 10-15). Un layer senza una sorgente verificata non si scrive e
  il motivo finisce in metadata["missing"] e nel report.
- basemap_<aoi>.json: report (file, dimensioni, conteggi, sorgenti, mancanze).

Le sorgenti vettoriali si scaricano qui (con cache in data/raw/<sorgente>/);
il DTM invece va scaricato prima con `fetch dtm --aoi <aoi>`.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .. import __version__
from ..build import attribution, licence_short
from ..config import Source, get_source, load_aois, load_sources
from ..errors import FiutoError, NotConfigured
from ..grid import Grid, resolve_aoi
from ..paths import BUILD_DIR

LAYERS = ("contours", "trails", "roads", "water", "places")
CREDIT = "Elaborazione fiuto."


@dataclass
class BasemapConfig:
    minzoom: int = 10
    maxzoom: int = 15
    dtm_res: float = 10.0  # m: il DTM a 5 m si media a 10 m (rilievo e curve)
    hillshade_azimuth: float = 315.0
    hillshade_altitude: float = 45.0
    hillshade_quality: int = 80  # WEBP
    contour_interval: float = 10.0
    contour_major: float = 50.0
    contour_smooth_passes: int = 1
    contour_min_length: float = 100.0  # m: anelli e pezzetti più corti si scartano
    contour_simplify: float = 2.0  # m (Douglas-Peucker)
    minor_minzoom: int = 13  # curve da 10 m solo da qui; sotto solo le maggiori
    roads_minor_minzoom: int = 12  # carrarecce e sentieri DBTR da qui; sotto solo le strade
    simplification: float | None = 1.0  # opzione SIMPLIFICATION del driver PMTiles (unità del tile)


def _log(msg: str) -> None:
    print(msg, flush=True)


def _source_meta(src: Source, layers: list[str]) -> dict:
    return {
        "id": src.id,
        "title": src.title,
        "license": licence_short(src.license),
        "status": src.status,
        "layers": layers,
    }


# --- DTM ------------------------------------------------------------------------------


def load_dtm(src: Source, aoi_cfg, res: float) -> tuple[np.ndarray, Grid]:
    """DTM sull'AOI a `res` metri (media), nel CRS della sorgente. NaN = nodata."""
    from rasterio.enums import Resampling

    from ..geoio import check_range, is_raster, resample_to_grid

    if not src.crs:
        raise FiutoError(f"[{src.id}] manca crs in sources.toml")
    path = src.data_path()
    if not is_raster(path):
        raise FiutoError(f"[{src.id}] {path} non è un raster")
    aoi = resolve_aoi(aoi_cfg, src.crs)
    grid = Grid.from_bounds(aoi.bounds, src.crs, res)
    nodata = src.attr("nodata")
    z = resample_to_grid(
        path,
        grid,
        resampling=Resampling.average,
        band=int(src.attr("band", 1)),
        default_crs=src.crs,
        nodata=float(nodata) if nodata not in (None, "") else None,
    )
    z = check_range(z, -50.0, 5000.0, what=f"[{src.id}] quota")
    if not np.isfinite(z).any():
        raise FiutoError(f"[{src.id}] nessun dato di quota sull'AOI: rifai `fetch dtm --aoi {aoi_cfg.name}`")
    return z, grid


# --- sorgenti vettoriali ------------------------------------------------------------


def _fetch_trails(src: Source, bbox4326, *, force: bool, log):
    import pyogrio

    from ..fetch.download import fetch_wfs
    from .vector import trails_gdf

    path = fetch_wfs(src, bbox4326, force=force, log=log)
    raw = pyogrio.read_dataframe(path)
    if raw.crs is None:
        raw = raw.set_crs(src.crs)
    a = src.attr
    for key in ("name_attr", "ref_attr", "kind_attr", "difficulty_attr"):
        if not a(key):
            raise NotConfigured(f"[{src.id}] attributes.{key} vuoto [da verificare]")
        if a(key) not in raw.columns:
            raise FiutoError(f"[{src.id}] campo {a(key)} assente nella risposta WFS")
    return trails_gdf(
        raw,
        name_attr=a("name_attr"),
        ref_attr=a("ref_attr"),
        kind_attr=a("kind_attr"),
        difficulty_attr=a("difficulty_attr"),
    )


def _rest_layer(src: Source, layer, bbox, fields: list[str], *, force: bool, log):
    from ..fetch.download import fetch_arcgis_layer

    gdf = fetch_arcgis_layer(src, layer, bbox, fields=fields, force=force, log=log)
    missing = [f for f in fields if not gdf.empty and f not in gdf.columns]
    if missing:
        raise FiutoError(f"[{src.id}] layer {layer}: campi {missing} assenti nella risposta")
    return gdf


def _fetch_roads(srcs: list[Source], bbox_by_src, *, force: bool, log):
    from .vector import roads_gdf

    by_kind = {}
    for src in srcs:
        layers = src.attr("roads_layers") or {}
        if not layers:
            raise NotConfigured(f"[{src.id}] attributes.roads_layers vuoto [da verificare]")
        for kind, lyr in layers.items():
            by_kind[kind] = _rest_layer(src, lyr, bbox_by_src[src.id], [], force=force, log=log)
            log(f"  roads/{kind}: {len(by_kind[kind])} elementi (layer {lyr})")
    return roads_gdf(by_kind)


# --- comando ------------------------------------------------------------------------


def run_basemap(
    aoi_name: str,
    *,
    sources_path: Path | None = None,
    aoi_path: Path | None = None,
    raw_dir: Path | None = None,
    out_dir: Path | None = None,
    only: str | None = None,
    force: bool = False,
    config: BasemapConfig | None = None,
    log=_log,
) -> dict:
    from .contours import contour_lines, smooth
    from .hillshade import hillshade, write_hillshade_pmtiles
    from .vector import (
        Part,
        check_parts,
        clip_wgs84,
        contours_gdf,
        merge_pmtiles,
        places_gdf,
        water_gdf,
        write_part,
        zoom_split,
    )

    cfg = config or BasemapConfig()
    sources = load_sources(sources_path, raw_dir=raw_dir)
    aois = load_aois(aoi_path)
    if aoi_name not in aois:
        raise FiutoError(f"AOI '{aoi_name}' non trovata (disponibili: {', '.join(aois)})")
    aoi_cfg = aois[aoi_name]
    out_dir = Path(out_dir) if out_dir else BUILD_DIR / aoi_name
    out_dir.mkdir(parents=True, exist_ok=True)
    built = datetime.now(UTC).isoformat(timespec="seconds")
    common = {
        "aoi": aoi_name,
        "built": built,
        "generator": f"fiuto_pipeline {__version__}",
    }
    if aoi_cfg.approximate:
        common["aoi_note"] = "AOI approssimativa: " + (aoi_cfg.description or "bbox scritto a mano")
    report: dict = {"aoi": aoi_name, "built": built, "config": asdict(cfg)}

    dtm = get_source(sources, "dtm")
    log(f"DTM da {dtm.data_path()} a {cfg.dtm_res:g} m")
    z, grid = load_dtm(dtm, aoi_cfg, cfg.dtm_res)
    report["dtm"] = {"crs": grid.crs, "res_m": cfg.dtm_res, "shape": list(grid.shape)}

    # 1. rilievo (raster)
    if only in (None, "rilievo"):
        gray, valid = hillshade(
            z, cfg.dtm_res, azimuth=cfg.hillshade_azimuth, altitude=cfg.hillshade_altitude
        )
        out = out_dir / f"rilievo_{aoi_name}.pmtiles"
        log(f"rilievo -> {out}")
        meta = {
            **common,
            "name": f"fiuto rilievo {aoi_name}",
            "description": (
                f"Rilievo ombreggiato dal DTM 5x5 a {cfg.dtm_res:g} m "
                f"(sole a {cfg.hillshade_azimuth:g}° e {cfg.hillshade_altitude:g}°)"
            ),
            "attribution": attribution([dtm], credit=CREDIT),
            "sources": [_source_meta(dtm, ["rilievo"])],
            "fiuto_rilievo": True,
        }
        report["rilievo"] = write_hillshade_pmtiles(
            gray,
            valid,
            grid.transform,
            grid.crs,
            out,
            minzoom=cfg.minzoom,
            maxzoom=cfg.maxzoom,
            metadata=meta,
            quality=cfg.hillshade_quality,
        )
        r = report["rilievo"]
        log(
            f"  {r['bytes'] / 1e6:.1f} MB, {r['tiles']} tile {r['format']}, zoom {r['min_zoom']}-{r['max_zoom']}"
        )
        if r.get("note"):
            log(f"  avviso: {r['note']}")

    # 2. base (vettoriale)
    if only in (None, "base"):
        aoi4326 = resolve_aoi(aoi_cfg, "EPSG:4326").bounds
        parts: list[Part] = []
        used: dict[str, tuple[Source, list[str]]] = {}
        missing: dict[str, str] = {}
        counts: dict[str, int] = {}

        def add(layer: str, new_parts: list[Part], srcs: list[Source]):
            parts.extend(new_parts)
            counts[layer] = max(len(p.gdf) for p in new_parts)
            for s in srcs:
                used.setdefault(s.id, (s, []))[1].append(layer)

        # contours: dal DTM
        log("contours: curve di livello")
        lines = contour_lines(
            smooth(z, passes=cfg.contour_smooth_passes),
            grid.transform,
            interval=cfg.contour_interval,
            major_every=cfg.contour_major,
            min_length=cfg.contour_min_length,
            simplify=cfg.contour_simplify,
        )
        cg = contours_gdf(lines, grid.crs)
        add(
            "contours",
            zoom_split(
                "contours",
                cg,
                cg["major"].to_numpy(dtype=bool),
                minzoom=cfg.minzoom,
                split=cfg.minor_minzoom,
                maxzoom=cfg.maxzoom,
                description=f"Curve di livello ogni {cfg.contour_interval:g} m dal DTM 5x5 (maggiori ogni {cfg.contour_major:g} m)",
            ),
            [dtm],
        )
        log(f"  {len(cg)} curve, {int(cg['major'].sum())} maggiori")

        def attempt(layer: str, fn):
            try:
                fn()
            except (NotConfigured, FiutoError) as exc:
                missing[layer] = str(exc).splitlines()[0]
                log(f"  {layer}: NON scritto ({missing[layer]})")

        def do_trails():
            src = get_source(sources, "sentieri")
            log("trails: rete escursionistica (WFS)")
            bbox = resolve_aoi(aoi_cfg, src.crs).bounds
            g = clip_wgs84(_fetch_trails(src, bbox, force=force, log=log), aoi4326)
            if g.empty:
                raise FiutoError("nessun percorso nell'AOI")
            add(
                "trails",
                [Part("trails", g, cfg.minzoom, cfg.maxzoom, "Rete escursionistica regionale (percorsi)")],
                [src],
            )
            log(f"  {len(g)} tratti")

        def do_roads():
            srcs = [get_source(sources, sid) for sid in ("dbtr", "dbtr_sentieri")]
            log("roads: DBTR (REST)")
            bboxes = {s.id: resolve_aoi(aoi_cfg, s.crs).bounds for s in srcs}
            g = clip_wgs84(_fetch_roads(srcs, bboxes, force=force, log=log), aoi4326)
            if g.empty:
                raise FiutoError("nessuna strada nell'AOI")
            add(
                "roads",
                zoom_split(
                    "roads",
                    g,
                    (g["kind"] == "strada").to_numpy(),
                    minzoom=cfg.minzoom,
                    split=cfg.roads_minor_minzoom,
                    maxzoom=cfg.maxzoom,
                    description="Viabilità DBTR: strada, carrareccia, sentiero",
                ),
                srcs,
            )

        def do_water():
            src = get_source(sources, "dbtr")
            name = src.attr("water_name_attr")
            if src.attr("water_layer") in (None, "") or not name:
                raise NotConfigured("[dbtr] water_layer/water_name_attr vuoti [da verificare]")
            log("water: corsi d'acqua DBTR (REST)")
            raw = _rest_layer(
                src,
                src.attr("water_layer"),
                resolve_aoi(aoi_cfg, src.crs).bounds,
                [name],
                force=force,
                log=log,
            )
            g = clip_wgs84(water_gdf(raw, name_attr=name), aoi4326)
            if g.empty:
                raise FiutoError("nessun corso d'acqua nell'AOI")
            add("water", [Part("water", g, cfg.minzoom, cfg.maxzoom, "Corsi d'acqua naturali (DBTR)")], [src])
            log(f"  {len(g)} tratti")

        def do_places():
            src = get_source(sources, "dbtr")
            name, kind = src.attr("places_name_attr"), src.attr("places_kind_attr")
            if src.attr("places_layer") in (None, "") or not name or not kind:
                raise NotConfigured(
                    "[dbtr] places_layer/places_name_attr/places_kind_attr vuoti [da verificare]"
                )
            log("places: località abitate DBTR (REST)")
            raw = _rest_layer(
                src,
                src.attr("places_layer"),
                resolve_aoi(aoi_cfg, src.crs).bounds,
                [name, kind],
                force=force,
                log=log,
            )
            g = clip_wgs84(places_gdf(raw, name_attr=name, kind_attr=kind), aoi4326)
            if g.empty:
                raise FiutoError("nessuna località nell'AOI")
            add("places", [Part("places", g, cfg.minzoom, cfg.maxzoom, "Località abitate (DBTR)")], [src])
            log(f"  {len(g)} località")

        for layer, fn in (
            ("trails", do_trails),
            ("roads", do_roads),
            ("water", do_water),
            ("places", do_places),
        ):
            attempt(layer, fn)

        check_parts(parts)
        out = out_dir / f"base_{aoi_name}.pmtiles"
        log(f"base -> {out}")
        srcs_used = [s for s, _ in used.values()]
        meta = {
            **common,
            "name": f"fiuto base {aoi_name}",
            "description": "Basemap offline: curve di livello, sentieri, strade, acque, località (dati regionali ER)",
            "attribution": attribution(srcs_used, credit=CREDIT),
            "fiuto_basemap": True,
            "sources": [_source_meta(s, ls) for s, ls in used.values()],
        }
        if missing:
            meta["missing"] = missing
        with tempfile.TemporaryDirectory() as td:
            paths = []
            for i, p in enumerate(parts):
                w = write_part(p, Path(td) / f"{i:02d}_{p.layer}.pmtiles", simplification=cfg.simplification)
                if w:
                    paths.append(w)
            res = merge_pmtiles(paths, out, meta, {p.layer: p.description for p in parts})
        res["features"] = counts
        res["missing"] = missing
        res["attribution"] = meta["attribution"]
        report["base"] = res
        log(f"  {res['bytes'] / 1e6:.1f} MB, {res['tiles']} tile, layer {sorted(res['tiles_per_layer'])}")
        if missing:
            log(f"  mancano: {', '.join(missing)}")

    rpath = out_dir / f"basemap_{aoi_name}.json"
    rpath.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    report["report_path"] = str(rpath)
    log(f"report -> {rpath}")
    return report
