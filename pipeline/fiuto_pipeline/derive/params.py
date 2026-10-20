"""Una funzione per ogni parametro VTH remoto.

Ogni funzione ritorna un `ParamResult` con un array uint8 sulla griglia
(punti 0..max, 255 = non disponibile). Soglie e categorie vengono dal modello.
Se la sorgente non è configurata si alza `NotConfigured` (il build salta il
parametro); se è configurata male si alza `ConfigError` (il build si ferma).
Con una tabella di lookup ancora vuota il parametro resta tutto 255, ma i
valori trovati nei dati vengono elencati (da classificare) con la superficie.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from rasterio.enums import Resampling

from ..config import Source
from ..errors import ConfigError
from ..geoio import (
    check_range,
    codes_from_index,
    is_raster,
    rasterize_codes,
    rasterize_index,
    rasterize_mask,
    rasterize_values,
    read_vector,
    resample_to_grid,
)
from ..grid import Grid
from ..lookups import Lookup, category_map, draft_count, int_map, load_lookup
from ..model import NA, Model

# Intervalli fisicamente plausibili: servono solo a scovare nodata/scale sbagliati.
PLAUSIBLE = {
    "elevation": (-50.0, 5000.0),  # m slm
    "ph": (2.0, 11.0),
    "caco3": (0.0, 100.0),  # %
}


@dataclass
class ParamResult:
    param: str
    array: np.ndarray
    source: str
    detail: str = ""
    unmapped: list[dict] = field(default_factory=list)
    lookup: str = ""  # tabella di lookup usata (per il CSV dei valori da classificare)
    drafts: int = 0  # righe della tabella segnate BOZZA


# --- mappature pure (testabili senza file) ----------------------------------


def _unmapped_report(
    codes: np.ndarray,
    labels: list[str],
    is_mapped: np.ndarray,
    cell_ha: float,
    mask: np.ndarray | None,
    lookup: Lookup | None,
    names: dict[str, str] | None,
) -> list[dict]:
    """Valori presenti nei dati ma senza classe, con superficie (ha), dal più esteso."""
    if not labels:
        return []
    valid = codes >= 0
    counts = np.bincount(codes[valid], minlength=len(labels))
    if mask is not None:
        counts_mask = np.bincount(codes[valid & mask], minlength=len(labels))
    out = []
    for i, label in enumerate(labels):
        if is_mapped[i] or counts[i] == 0:
            continue
        row = {
            "value": label,
            "name": (names or {}).get(label, ""),
            "ha": round(float(counts[i]) * cell_ha, 4),
            "in_table": bool(lookup and label in lookup.rows),
        }
        if mask is not None:
            row["ha_bosco"] = round(float(counts_mask[i]) * cell_ha, 4)
        out.append(row)
    key = "ha_bosco" if mask is not None else "ha"
    out.sort(key=lambda r: (-r[key], -r["ha"], r["value"]))
    return out


def map_categories(
    codes: np.ndarray,
    labels: list[str],
    value_to_category: dict[str, str],
    category_points: dict[str, int],
    *,
    cell_ha: float = 0.0,
    mask: np.ndarray | None = None,
    lookup: Lookup | None = None,
    names: dict[str, str] | None = None,
) -> tuple[np.ndarray, list[dict]]:
    """Indici (da `rasterize_codes`) -> punti del modello, più elenco dei non mappati."""
    pts_by_idx = np.full(len(labels) + 1, NA, dtype="uint8")  # ultimo = -1 (assente)
    is_mapped = np.zeros(len(labels), dtype=bool)
    for i, label in enumerate(labels):
        cat = value_to_category.get(label)
        if cat is not None:
            pts_by_idx[i] = category_points[cat]
            is_mapped[i] = True
    out = pts_by_idx[codes]  # codes == -1 -> ultimo elemento (NA)
    return out, _unmapped_report(codes, labels, is_mapped, cell_ha, mask, lookup, names)


def map_ints(
    codes: np.ndarray,
    labels: list[str],
    value_to_points: dict[str, int],
    *,
    cell_ha: float = 0.0,
    mask: np.ndarray | None = None,
    lookup: Lookup | None = None,
    names: dict[str, str] | None = None,
) -> tuple[np.ndarray, list[dict]]:
    """Come `map_categories`, ma la tabella dà direttamente i punti (es. ospiti 0/1)."""
    pts_by_idx = np.full(len(labels) + 1, NA, dtype="uint8")
    is_mapped = np.zeros(len(labels), dtype=bool)
    for i, label in enumerate(labels):
        if label in value_to_points:
            pts_by_idx[i] = value_to_points[label]
            is_mapped[i] = True
    out = pts_by_idx[codes]
    return out, _unmapped_report(codes, labels, is_mapped, cell_ha, mask, lookup, names)


def _names(gdf, code_attr: str, name_attr: str | None) -> dict[str, str]:
    """Primo nome trovato per ogni codice (solo per rendere leggibili i report)."""
    from ..lookups import norm_key

    if not name_attr:
        return {}
    out: dict[str, str] = {}
    for c, n in zip(gdf[code_attr], gdf[name_attr]):
        k = norm_key(c)
        if k is not None and k not in out and norm_key(n):
            out[k] = str(n).strip()
    return out


def _float_or_none(v) -> float | None:
    return None if v is None or v == "" else float(v)


# --- parametri numerici -------------------------------------------------------


def derive_elevation(src: Source, grid: Grid, model: Model) -> ParamResult:
    """Quota: DTM (qualsiasi CRS) -> media sulla cella -> regole del modello."""
    path = src.data_path()
    if not is_raster(path):
        raise ConfigError(f"[{src.id}] {path} non è un raster: per la quota serve un DTM")
    z = resample_to_grid(
        path,
        grid,
        resampling=Resampling.average,
        band=int(src.attr("band", 1)),
        default_crs=src.crs,
        nodata=_float_or_none(src.attr("nodata")),
    )
    z = check_range(z, *PLAUSIBLE["elevation"], what=f"[{src.id}] quota")
    return ParamResult("elevation", model.classify("elevation", z), src.id, f"{path}")


def _numeric_from(src: Source, grid: Grid, attr_key: str, what: str) -> tuple[np.ndarray, str]:
    """Valori numerici da raster (media) o da vettore (attributo indicato in config)."""
    path = src.data_path()
    scale = float(src.attr("value_scale", 1.0))
    if is_raster(path):
        vals = resample_to_grid(
            path,
            grid,
            resampling=Resampling.average,
            band=int(src.attr("band", 1)),
            default_crs=src.crs,
            scale=scale,
            nodata=_float_or_none(src.attr("nodata")),
        )
        return vals, f"{path} (raster)"
    src.require("attributes", attr_key, what=what)
    attr = src.attr(attr_key)
    gdf = read_vector(path, grid, sid=src.id, layer=src.attr("layer"), columns=[attr], default_crs=src.crs)
    vals = rasterize_values(gdf, attr, grid)
    if scale != 1.0:
        vals *= np.float32(scale)
    return vals, f"{path} attributo {attr}"


def derive_ph(src: Source, grid: Grid, model: Model) -> ParamResult:
    """pH 0-30 cm: raster o vettore con attributo numerico (attributes.ph_attr)."""
    vals, detail = _numeric_from(src, grid, "ph_attr", "il pH da vettore")
    vals = check_range(vals, *PLAUSIBLE["ph"], what=f"[{src.id}] pH")
    return ParamResult("ph", model.classify("ph", vals), src.id, detail)


def derive_caco3(src: Source, grid: Grid, model: Model) -> ParamResult:
    """CaCO3 %: attributo numerico della carta dei suoli (attributes.caco3_attr)."""
    src.require("attributes", "caco3_attr", what="il CaCO3")
    path = src.data_path()
    attr = src.attr("caco3_attr")
    gdf = read_vector(path, grid, sid=src.id, layer=src.attr("layer"), columns=[attr], default_crs=src.crs)
    vals = rasterize_values(gdf, attr, grid)
    vals = check_range(vals, *PLAUSIBLE["caco3"], what=f"[{src.id}] CaCO3")
    return ParamResult("caco3", model.classify("caco3", vals), src.id, f"{path} attributo {attr}")


# --- parametri a categorie (via lookup) ----------------------------------------


def _empty_note(lookup: Lookup, column: str) -> str:
    """Con la tabella vuota il parametro resta tutto 255, ma i valori vengono elencati."""
    if lookup.mapped_count(column) == 0:
        return f"; tabella {lookup.path.name} senza '{column}': tutti i valori sono da classificare"
    return ""


def derive_texture(
    src: Source, grid: Grid, model: Model, *, mask: np.ndarray | None = None, lookup_dir: Path | None = None
) -> ParamResult:
    """Tessitura: attributo suoli -> lookups/suoli_tessitura.csv -> categoria -> punti."""
    src.require("attributes", "texture_attr", what="la tessitura")
    lookup = load_lookup("suoli_tessitura", lookup_dir)
    cats = model.categories("texture")
    mapping = category_map(lookup, "texture_id", cats)
    path = src.data_path()
    attr = src.attr("texture_attr")
    gdf = read_vector(path, grid, sid=src.id, layer=src.attr("layer"), columns=[attr], default_crs=src.crs)
    codes, labels = rasterize_codes(gdf, attr, grid)
    pts, unmapped = map_categories(
        codes, labels, mapping, cats, cell_ha=grid.cell_area_ha, mask=mask, lookup=lookup
    )
    detail = f"{path} attributo {attr}" + _empty_note(lookup, "texture_id")
    return ParamResult("texture", pts, src.id, detail, unmapped, lookup.name, draft_count(lookup))


def derive_bedrock(
    src: Source, grid: Grid, model: Model, *, mask: np.ndarray | None = None, lookup_dir: Path | None = None
) -> ParamResult:
    """Roccia madre: unità geologica -> lookups/geologia_vth.csv -> classe VTH -> punti."""
    src.require("attributes", "unit_code_attr", what="la roccia madre")
    lookup = load_lookup("geologia_vth", lookup_dir)
    cats = model.categories("bedrock")
    mapping = category_map(lookup, "vth_class", cats)
    path = src.data_path()
    code_attr = src.attr("unit_code_attr")
    name_attr = src.attr("unit_name_attr")
    cols = [code_attr] + ([name_attr] if name_attr else [])
    gdf = read_vector(path, grid, sid=src.id, layer=src.attr("layer"), columns=cols, default_crs=src.crs)
    codes, labels = rasterize_codes(gdf, code_attr, grid)
    pts, unmapped = map_categories(
        codes,
        labels,
        mapping,
        cats,
        cell_ha=grid.cell_area_ha,
        mask=mask,
        lookup=lookup,
        names=_names(gdf, code_attr, name_attr),
    )
    detail = f"{path} attributo {code_attr}" + _empty_note(lookup, "vth_class")
    return ParamResult("bedrock", pts, src.id, detail, unmapped, lookup.name, draft_count(lookup))


def _read_forest(src: Source, grid: Grid, columns: list[str]):
    path = src.data_path()
    gdf = read_vector(
        path,
        grid,
        sid=src.id,
        layer=src.attr("layer"),
        columns=columns,
        default_crs=src.crs,
        where=src.attr("mask_where"),
    )
    return path, gdf


def derive_forest_mask(src: Source, grid: Grid) -> tuple[np.ndarray, str]:
    """Maschera bosco: qualsiasi poligono della carta forestale (filtrabile con mask_where)."""
    path, gdf = _read_forest(src, grid, [])
    where = src.attr("mask_where")
    detail = f"{path}" + (f" where {where}" if where else " (tutti i poligoni)")
    return rasterize_mask(gdf, grid), detail


def combine_hosts(values: list[np.ndarray], present: list[np.ndarray]) -> np.ndarray:
    """Ospiti da più specie (es. prima e seconda specie prevalente).

    1 se almeno una specie è ospite; 0 se tutte le specie presenti sono
    classificate non ospiti; 255 se manca il dato o una specie presente non
    è ancora in tabella (prudenza: non si dà 0 su un'incognita).
    """
    any_host = np.zeros(values[0].shape, dtype=bool)
    unknown = np.zeros(values[0].shape, dtype=bool)
    any_present = np.zeros(values[0].shape, dtype=bool)
    for v, pr in zip(values, present):
        any_host |= v == 1
        unknown |= pr & (v == NA)
        any_present |= pr
    out = np.full(values[0].shape, NA, dtype="uint8")
    out[any_present & ~unknown] = 0
    out[any_host] = 1
    return out


def _as_list(v) -> list[str]:
    if v is None:
        return []
    return [str(x) for x in v] if isinstance(v, (list, tuple)) else [str(v)]


def _merge_unmapped(lists: list[list[dict]], mask: np.ndarray | None) -> list[dict]:
    """Unisce i valori non classificati di più attributi sommando le superfici."""
    merged: dict[str, dict] = {}
    for rows in lists:
        for r in rows:
            m = merged.setdefault(
                r["value"], {**r, "ha": 0.0, **({"ha_bosco": 0.0} if mask is not None else {})}
            )
            m["ha"] = round(m["ha"] + r["ha"], 4)
            if mask is not None:
                m["ha_bosco"] = round(m["ha_bosco"] + r.get("ha_bosco", 0.0), 4)
            m["name"] = m.get("name") or r.get("name", "")
    key = "ha_bosco" if mask is not None else "ha"
    return sorted(merged.values(), key=lambda r: (-r[key], -r["ha"], r["value"]))


def derive_forest(
    src: Source, grid: Grid, model: Model, *, mask: np.ndarray | None = None, lookup_dir: Path | None = None
) -> dict[str, ParamResult]:
    """Tipo di bosco e ospiti dalla carta forestale.

    Tipo: attributes.forest_type_attr -> lookups/forestale_vth.csv (forest_class).
    Ospiti: se attributes.hosts_attrs elenca attributi di specie (es. prima e
    seconda specie prevalente) -> lookups/forestale_specie.csv (host 0/1),
    altrimenti la colonna hosts di forestale_vth.csv per tipo.
    Con le tabelle ancora vuote i parametri restano a 255 ma i valori trovati
    finiscono nel report.
    """
    src.require("attributes", "forest_type_attr", what="tipo di bosco e ospiti")
    lookup = load_lookup("forestale_vth", lookup_dir)
    cats = model.categories("forest_type")
    mapping = category_map(lookup, "forest_class", cats)
    code_attr = src.attr("forest_type_attr")
    name_attr = src.attr("forest_type_name_attr")
    hosts_attrs = _as_list(src.attr("hosts_attrs"))
    hosts_names = _as_list(src.attr("hosts_name_attrs"))
    if hosts_names and len(hosts_names) != len(hosts_attrs):
        raise ConfigError(f"[{src.id}] hosts_name_attrs deve avere tanti elementi quanti hosts_attrs")
    cols = list(dict.fromkeys([code_attr] + ([name_attr] if name_attr else []) + hosts_attrs + hosts_names))
    path, gdf = _read_forest(src, grid, cols)
    gdf = gdf.reset_index(drop=True)
    index = rasterize_index(gdf, grid)
    codes, labels = codes_from_index(index, gdf[code_attr].tolist())
    common = dict(cell_ha=grid.cell_area_ha, mask=mask)
    detail = f"{path} attributo {code_attr}"

    pts, unmapped = map_categories(
        codes, labels, mapping, cats, lookup=lookup, names=_names(gdf, code_attr, name_attr), **common
    )
    ft = ParamResult(
        "forest_type",
        pts,
        src.id,
        detail + _empty_note(lookup, "forest_class"),
        unmapped,
        lookup.name,
        draft_count(lookup),
    )

    if hosts_attrs:
        sp_lookup = load_lookup("forestale_specie", lookup_dir)
        sp_map = int_map(sp_lookup, "host", model.remote_max("hosts"))
        values, present, unm = [], [], []
        for i, a in enumerate(hosts_attrs):
            c, lab = codes_from_index(index, gdf[a].tolist())
            names = _names(gdf, a, hosts_names[i]) if hosts_names else {}
            v, u = map_ints(c, lab, sp_map, lookup=sp_lookup, names=names, **common)
            values.append(v)
            present.append(c >= 0)
            unm.append(u)
        hosts = ParamResult(
            "hosts",
            combine_hosts(values, present),
            src.id,
            f"{path} attributi {', '.join(hosts_attrs)}" + _empty_note(sp_lookup, "host"),
            _merge_unmapped(unm, mask),
            sp_lookup.name,
            draft_count(sp_lookup),
        )
    else:
        mapping_h = int_map(lookup, "hosts", model.remote_max("hosts"))
        pts_h, unmapped_h = map_ints(
            codes, labels, mapping_h, lookup=lookup, names=_names(gdf, code_attr, name_attr), **common
        )
        hosts = ParamResult(
            "hosts",
            pts_h,
            src.id,
            detail + _empty_note(lookup, "hosts"),
            unmapped_h,
            lookup.name,
            draft_count(lookup),
        )
    return {"forest_type": ft, "hosts": hosts}
