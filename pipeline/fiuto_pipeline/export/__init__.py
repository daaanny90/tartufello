"""Export: poligoni per combinazione di punti -> GeoJSONSeq + PMTiles vettoriale."""

from .polygonize import contract_keys, decode, encode, feature_properties, polygonize, properties_table
from .tiles import (
    METHOD_GDAL_MBTILES,
    METHOD_GDAL_PMTILES,
    METHOD_NONE,
    available_method,
    set_pmtiles_metadata,
    tippecanoe_hint,
    write_geojsonseq,
    write_pmtiles,
)
from .verify import verify_pmtiles

__all__ = [
    "METHOD_GDAL_MBTILES",
    "METHOD_GDAL_PMTILES",
    "METHOD_NONE",
    "available_method",
    "contract_keys",
    "decode",
    "encode",
    "export_vth",
    "feature_properties",
    "polygonize",
    "properties_table",
    "set_pmtiles_metadata",
    "tippecanoe_hint",
    "verify_pmtiles",
    "write_geojsonseq",
    "write_pmtiles",
]


def export_vth(
    params,
    mask,
    grid,
    model,
    out_dir,
    *,
    stem: str,
    minzoom: int,
    maxzoom: int,
    name: str,
    description: str,
    metadata: dict,
    simplification: float | None = None,
    simplification_max_zoom: float | None = None,
    method: str | None = None,
    verify_max_tiles: int | None = None,
    geojsonseq: bool = True,
) -> dict:
    """Percorso completo: poligonizza, riproietta in EPSG:4326, scrive e verifica.

    Usato sia dal build sia dallo script della fixture sintetica.
    """
    from pathlib import Path

    out_dir = Path(out_dir)
    keys = contract_keys(model)
    gdf = polygonize(params, mask, grid, model).to_crs("EPSG:4326")
    out = {"features": int(len(gdf))}
    if geojsonseq or method == METHOD_NONE:
        out["geojsonseq"] = str(write_geojsonseq(gdf, out_dir / f"{stem}.geojsonl", keys))
    info = write_pmtiles(
        gdf,
        out_dir / f"{stem}.pmtiles",
        keys=keys,
        layer=model.tile_layer,
        minzoom=minzoom,
        maxzoom=maxzoom,
        name=name,
        description=description,
        metadata=metadata,
        simplification=simplification,
        simplification_max_zoom=simplification_max_zoom,
        method=method,
    )
    out["tiles"] = info
    if info["path"]:
        out["verify"] = verify_pmtiles(Path(info["path"]), model, max_tiles=verify_max_tiles)
    else:
        out["hint"] = tippecanoe_hint(
            Path(out["geojsonseq"]), out_dir / f"{stem}.pmtiles", model.tile_layer, minzoom, maxzoom
        )
    return out
