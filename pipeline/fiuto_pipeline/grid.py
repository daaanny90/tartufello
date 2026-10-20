"""Griglia comune di lavoro (EPSG:5659, celle da 20-25 m) e area di interesse."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from affine import Affine
from pyproj import CRS, Transformer
from rasterio.features import rasterize

from .config import AOIConfig
from .errors import ConfigError


@dataclass(frozen=True)
class Grid:
    crs: str
    transform: Affine
    width: int
    height: int

    @classmethod
    def from_bounds(cls, bounds: tuple[float, float, float, float], crs: str, cell_size: float) -> Grid:
        """Griglia allineata a multipli di cell_size che copre `bounds` (allargando)."""
        minx, miny, maxx, maxy = bounds
        x0 = math.floor(minx / cell_size) * cell_size
        y0 = math.floor(miny / cell_size) * cell_size
        x1 = math.ceil(maxx / cell_size) * cell_size
        y1 = math.ceil(maxy / cell_size) * cell_size
        width = int(round((x1 - x0) / cell_size))
        height = int(round((y1 - y0) / cell_size))
        if width <= 0 or height <= 0:
            raise ConfigError("griglia vuota: controlla il bbox dell'AOI")
        return cls(crs=crs, transform=Affine(cell_size, 0, x0, 0, -cell_size, y1), width=width, height=height)

    @property
    def cell_size(self) -> float:
        return float(self.transform.a)

    @property
    def shape(self) -> tuple[int, int]:
        return (self.height, self.width)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        x0, y1 = self.transform.c, self.transform.f
        return (x0, y1 - self.height * self.cell_size, x0 + self.width * self.cell_size, y1)

    @property
    def cell_area_ha(self) -> float:
        return self.cell_size * self.cell_size / 10_000.0

    def bounds_in(self, crs: str | CRS) -> tuple[float, float, float, float]:
        if CRS.from_user_input(crs) == CRS.from_user_input(self.crs):
            return self.bounds
        t = Transformer.from_crs(self.crs, crs, always_xy=True)
        return t.transform_bounds(*self.bounds, densify_pts=21)


@dataclass
class AOI:
    name: str
    description: str
    approximate: bool
    bounds: tuple[float, float, float, float]  # nel CRS di lavoro
    geometry: object | None  # shapely, nel CRS di lavoro (None = solo bbox)

    def mask(self, grid: Grid) -> np.ndarray:
        """True dentro l'AOI. Con il solo bbox è tutta la griglia."""
        if self.geometry is None:
            return np.ones(grid.shape, dtype=bool)
        return rasterize(
            [(self.geometry, 1)], out_shape=grid.shape, transform=grid.transform, fill=0, dtype="uint8"
        ).astype(bool)


def resolve_aoi(cfg: AOIConfig, work_crs: str) -> AOI:
    if cfg.bbox is not None:
        if CRS.from_user_input(cfg.crs) == CRS.from_user_input(work_crs):
            bounds = cfg.bbox
        else:
            t = Transformer.from_crs(cfg.crs, work_crs, always_xy=True)
            bounds = t.transform_bounds(*cfg.bbox, densify_pts=21)
        return AOI(cfg.name, cfg.description, cfg.approximate, tuple(bounds), None)

    import geopandas as gpd

    if not cfg.path or not cfg.path.exists():
        raise ConfigError(f"[aoi.{cfg.name}] file non trovato: {cfg.path}")
    gdf = gpd.read_file(cfg.path, layer=cfg.layer) if cfg.layer else gpd.read_file(cfg.path)
    if gdf.empty:
        raise ConfigError(f"[aoi.{cfg.name}] il file {cfg.path} non contiene geometrie")
    if gdf.crs is None:
        raise ConfigError(f"[aoi.{cfg.name}] il file {cfg.path} non dichiara il CRS")
    geom = gdf.to_crs(work_crs).geometry.union_all()
    return AOI(cfg.name, cfg.description, cfg.approximate, tuple(geom.bounds), geom)


def fetch_bbox(
    cfg: AOIConfig, src_crs: str, margin_m: float, metric_crs: str = "EPSG:5659"
) -> tuple[float, float, float, float]:
    """Bbox dell'AOI nel CRS della sorgente, allargato di `margin_m` metri.

    Con un CRS proiettato il margine si somma direttamente; con un CRS geografico
    (gradi, es. EPSG:4326) si allarga nel CRS metrico e poi si riproietta.
    """
    crs = CRS.from_user_input(src_crs)
    if crs.is_projected:
        b = resolve_aoi(cfg, src_crs).bounds
        return (b[0] - margin_m, b[1] - margin_m, b[2] + margin_m, b[3] + margin_m)
    b = resolve_aoi(cfg, metric_crs).bounds
    padded = (b[0] - margin_m, b[1] - margin_m, b[2] + margin_m, b[3] + margin_m)
    t = Transformer.from_crs(metric_crs, crs, always_xy=True)
    return tuple(t.transform_bounds(*padded, densify_pts=21))
