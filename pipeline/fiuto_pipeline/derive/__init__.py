"""Parametri VTH sulla griglia comune: array uint8, 255 = non disponibile."""

from .params import (
    ParamResult,
    derive_bedrock,
    derive_caco3,
    derive_elevation,
    derive_forest,
    derive_forest_mask,
    derive_ph,
    derive_texture,
    map_categories,
    map_ints,
)

__all__ = [
    "ParamResult",
    "derive_bedrock",
    "derive_caco3",
    "derive_elevation",
    "derive_forest",
    "derive_forest_mask",
    "derive_ph",
    "derive_texture",
    "map_categories",
    "map_ints",
]
