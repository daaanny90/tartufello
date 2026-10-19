"""Scarico dati regionali (WMS/WFS/WCS/zip) con cache locale in data/raw/."""

from .capabilities import run_capabilities
from .download import choose_method, fetch_url, fetch_wcs, fetch_wfs, run_fetch

__all__ = ["choose_method", "fetch_url", "fetch_wcs", "fetch_wfs", "run_capabilities", "run_fetch"]
