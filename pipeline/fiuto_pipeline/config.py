"""Lettura di sources.toml, aoi.toml e build.toml.

Regola d'oro: un identificativo vuoto resta vuoto. Il codice non indovina
layer, attributi o coverage: se mancano, si ferma e dice cosa verificare.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import ConfigError, NotConfigured
from .paths import DEFAULT_AOI, DEFAULT_BUILD, DEFAULT_SOURCES, PIPELINE_DIR, RAW_DIR, resolve

STATUS_OK = "ok"
STATUS_TODO = "da verificare"
STATUS_NOT_FOUND = "non trovato"
KNOWN_STATUS = {STATUS_OK, STATUS_TODO, STATUS_NOT_FOUND}

MANIFEST_NAME = "fetched.json"


def _read_toml(path: Path) -> dict:
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"file di configurazione non trovato: {path}") from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: TOML non valido ({exc})") from exc


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


@dataclass
class Source:
    id: str
    title: str = ""
    use: str = ""
    params: list[str] = field(default_factory=list)
    status: str = STATUS_TODO
    status_note: str = ""
    license: str = ""
    crs: str = ""
    local_path: str = ""
    endpoints: dict[str, str] = field(default_factory=dict)
    service: dict[str, Any] = field(default_factory=dict)
    attributes: dict[str, Any] = field(default_factory=dict)
    prepare: dict[str, Any] = field(default_factory=dict)
    base_dir: Path = PIPELINE_DIR
    raw_dir: Path = RAW_DIR

    # --- valori -----------------------------------------------------------
    def endpoint(self, kind: str) -> str:
        v = self.endpoints.get(kind, "")
        return "" if _is_empty(v) else str(v).strip()

    def attr(self, key: str, default: Any = None) -> Any:
        v = self.attributes.get(key, default)
        return default if _is_empty(v) else v

    def svc(self, key: str, default: Any = None) -> Any:
        v = self.service.get(key, default)
        return default if _is_empty(v) else v

    def prep(self, key: str, default: Any = None) -> Any:
        v = self.prepare.get(key, default)
        return default if _is_empty(v) else v

    def missing(self, section: str, *keys: str) -> list[str]:
        table = {
            "attributes": self.attributes,
            "service": self.service,
            "endpoints": self.endpoints,
            "prepare": self.prepare,
        }[section]
        return [f"{section}.{k}" for k in keys if _is_empty(table.get(k))]

    def require(self, section: str, *keys: str, what: str = "") -> None:
        """Errore chiaro se mancano identificativi: niente valori di ripiego."""
        miss = self.missing(section, *keys)
        if miss:
            hint = what or "questo passo"
            raise NotConfigured(
                f"[{self.id}] per {hint} mancano in sources.toml: {', '.join(miss)} "
                f"[da verificare]. Lancia `python -m fiuto_pipeline capabilities {self.id}` "
                f"(o guarda il file scaricato) e riempi i valori a mano."
            )

    # --- dati locali ------------------------------------------------------
    @property
    def cache_dir(self) -> Path:
        return self.raw_dir / self.id

    def manifest(self) -> dict | None:
        p = self.cache_dir / MANIFEST_NAME
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def data_path(self) -> Path:
        """File (o cartella) da cui leggere i dati.

        Ordine: `local_path` in sources.toml, poi l'ultimo `fetch` in cache.
        """
        if not _is_empty(self.local_path):
            p = resolve(self.local_path, self.base_dir)
            if not p.exists():
                raise ConfigError(f"[{self.id}] local_path non esiste: {p}")
            return p
        man = self.manifest()
        if man and man.get("path") and Path(man["path"]).exists():
            return Path(man["path"])
        raise NotConfigured(
            f"[{self.id}] nessun dato locale: local_path vuoto e niente in cache "
            f"({self.cache_dir}). Scarica il dato (fetch {self.id}) o imposta local_path."
        )

    def has_data(self) -> bool:
        try:
            self.data_path()
            return True
        except (NotConfigured, ConfigError):
            return False


def load_sources(path: str | Path | None = None, raw_dir: Path | None = None) -> dict[str, Source]:
    p = Path(path) if path else DEFAULT_SOURCES
    data = _read_toml(p)
    defaults = data.get("defaults", {})
    out: dict[str, Source] = {}
    for sid, s in data.get("sources", {}).items():
        status = str(s.get("status", STATUS_TODO)).strip()
        if status not in KNOWN_STATUS:
            raise ConfigError(
                f"{p}: [sources.{sid}] status '{status}' non valido "
                f"(ammessi: {', '.join(sorted(KNOWN_STATUS))})"
            )
        out[sid] = Source(
            id=sid,
            title=s.get("title", ""),
            use=s.get("use", ""),
            params=list(s.get("params", [])),
            status=status,
            status_note=s.get("status_note", ""),
            license=s.get("license", ""),
            crs=s.get("crs", defaults.get("crs", "")),
            local_path=s.get("local_path", ""),
            endpoints=dict(s.get("endpoints", {})),
            service=dict(s.get("service", {})),
            attributes=dict(s.get("attributes", {})),
            prepare=dict(s.get("prepare", {})),
            base_dir=p.parent,
            raw_dir=raw_dir or RAW_DIR,
        )
    return out


def get_source(sources: dict[str, Source], sid: str) -> Source:
    try:
        return sources[sid]
    except KeyError:
        raise ConfigError(
            f"sorgente '{sid}' non trovata in sources.toml (disponibili: {', '.join(sources)})"
        ) from None


# --- AOI -------------------------------------------------------------------


@dataclass
class AOIConfig:
    name: str
    description: str = ""
    approximate: bool = False
    bbox: tuple[float, float, float, float] | None = None
    crs: str = ""
    path: Path | None = None
    layer: str | None = None


def load_aois(path: str | Path | None = None) -> dict[str, AOIConfig]:
    p = Path(path) if path else DEFAULT_AOI
    data = _read_toml(p)
    out = {}
    for name, a in data.get("aoi", {}).items():
        bbox = a.get("bbox")
        apath = a.get("path", "")
        if bool(bbox) == bool(apath):
            raise ConfigError(f"{p}: [aoi.{name}] serve bbox OPPURE path (uno solo)")
        if bbox is not None:
            if len(bbox) != 4:
                raise ConfigError(f"{p}: [aoi.{name}] bbox deve avere 4 numeri: minx, miny, maxx, maxy")
            if not a.get("crs"):
                raise ConfigError(f"{p}: [aoi.{name}] con bbox serve crs (EPSG:4326 o EPSG:5659)")
            minx, miny, maxx, maxy = (float(v) for v in bbox)
            if minx >= maxx or miny >= maxy:
                raise ConfigError(f"{p}: [aoi.{name}] bbox con min >= max")
            bbox = (minx, miny, maxx, maxy)
        out[name] = AOIConfig(
            name=name,
            description=a.get("description", ""),
            approximate=bool(a.get("approximate", False)),
            bbox=bbox,
            crs=a.get("crs", ""),
            path=resolve(apath, p.parent) if apath else None,
            layer=a.get("layer") or None,
        )
    return out


# --- build -----------------------------------------------------------------

CELL_SIZE_RANGE = (20.0, 25.0)  # brief §5: niente precisione finta sotto i 20 m


@dataclass
class BuildConfig:
    model_path: Path
    crs: str = "EPSG:5659"
    cell_size: float = 25.0
    minzoom: int = 8
    maxzoom: int = 14
    simplification: float | None = None
    simplification_max_zoom: float | None = None
    verify_max_tiles: int = 300


def load_build_config(path: str | Path | None = None) -> BuildConfig:
    p = Path(path) if path else DEFAULT_BUILD
    data = _read_toml(p)
    grid = data.get("grid", {})
    exp = data.get("export", {})
    cfg = BuildConfig(
        model_path=resolve(data.get("model", "../model/vth-v2.json"), p.parent),
        crs=grid.get("crs", "EPSG:5659"),
        cell_size=float(grid.get("cell_size", 25)),
        minzoom=int(exp.get("minzoom", 8)),
        maxzoom=int(exp.get("maxzoom", 14)),
        simplification=exp.get("simplification"),
        simplification_max_zoom=exp.get("simplification_max_zoom"),
        verify_max_tiles=int(exp.get("verify_max_tiles", 300)),
    )
    lo, hi = CELL_SIZE_RANGE
    if not lo <= cfg.cell_size <= hi:
        raise ConfigError(
            f"{p}: grid.cell_size = {cfg.cell_size} m fuori da {lo:g}-{hi:g} m. "
            f"I suoli sono al 50.000: sotto i 20 m è precisione finta (BRIEF §5)."
        )
    if not 0 <= cfg.minzoom <= cfg.maxzoom <= 22:
        raise ConfigError(f"{p}: export.minzoom/maxzoom non validi")
    return cfg
