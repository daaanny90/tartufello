"""Percorsi standard della pipeline (tutti relativi alla cartella pipeline/)."""

from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = PIPELINE_DIR.parent

DEFAULT_SOURCES = PIPELINE_DIR / "sources.toml"
DEFAULT_AOI = PIPELINE_DIR / "aoi.toml"
DEFAULT_BUILD = PIPELINE_DIR / "build.toml"
LOOKUPS_DIR = PIPELINE_DIR / "lookups"

# Dati scaricati e prodotti: fuori da git (vedi .gitignore).
DATA_DIR = PIPELINE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
BUILD_DIR = DATA_DIR / "build"


def resolve(path: str | Path, base: Path = PIPELINE_DIR) -> Path:
    """Percorso assoluto: i relativi si intendono rispetto a `base`."""
    p = Path(path).expanduser()
    return p if p.is_absolute() else (base / p).resolve()
