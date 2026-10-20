"""Preparazione di dati derivati prima del build (es. proprietà 0-30 cm dalla carta dei suoli)."""

from .suoli import aggregate_profile, prepare_suoli, usda_texture

__all__ = ["aggregate_profile", "prepare_suoli", "usda_texture"]
