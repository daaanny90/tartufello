"""Tabelle di lookup (CSV in pipeline/lookups/): valore ER -> classe VTH.

Righe che iniziano con '#' sono commenti. Le tabelle si riempiono a mano a
partire dai valori reali dei dati regionali: il codice non ne inventa.
Valori non presenti (o con classe vuota) = parametro non disponibile (255).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ConfigError
from .paths import LOOKUPS_DIR

# nome file -> (colonna chiave, colonne obbligatorie)
SPECS = {
    "suoli_tessitura": ("valore_er", ["valore_er", "texture_id", "note", "fonte"]),
    "geologia_vth": ("unit_code", ["unit_code", "unit_name", "vth_class", "note", "fonte"]),
    "forestale_vth": ("tipo_er", ["tipo_er", "tipo_er_nome", "forest_class", "hosts", "note", "fonte"]),
    "forestale_specie": ("specie_er", ["specie_er", "specie_nome", "host", "note", "fonte"]),
}


def norm_key(value) -> str | None:
    """Normalizza un valore di attributo per il confronto con la tabella.

    Stringhe: spazi esterni tolti, maiuscole/minuscole invariate.
    Numeri interi letti come float (12.0) diventano "12".
    """
    if value is None:
        return None
    if isinstance(value, float):
        if value != value:  # NaN
            return None
        if value.is_integer():
            value = int(value)
    s = str(value).strip()
    return s or None


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Legge il CSV saltando righe vuote e commenti (#). Ritorna header e righe."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise ConfigError(f"tabella di lookup non trovata: {path}") from None
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        raise ConfigError(f"{path}: manca la riga di intestazione")
    reader = csv.DictReader(lines)
    header = [h.strip() for h in (reader.fieldnames or [])]
    rows = []
    for raw in reader:
        rows.append({(k or "").strip(): (v or "").strip() for k, v in raw.items()})
    return header, rows


@dataclass
class Lookup:
    name: str
    path: Path
    key: str
    rows: dict[str, dict[str, str]] = field(default_factory=dict)

    def get(self, value) -> dict[str, str] | None:
        k = norm_key(value)
        return None if k is None else self.rows.get(k)

    def mapped_count(self, column: str) -> int:
        return sum(1 for r in self.rows.values() if r.get(column))


def load_lookup(name: str, directory: Path | None = None) -> Lookup:
    if name not in SPECS:
        raise ConfigError(f"lookup sconosciuta: {name}")
    key, required = SPECS[name]
    path = (directory or LOOKUPS_DIR) / f"{name}.csv"
    header, rows = read_rows(path)
    missing = [c for c in required if c not in header]
    if missing:
        raise ConfigError(f"{path}: mancano le colonne {', '.join(missing)} (attese: {', '.join(required)})")
    out: dict[str, dict[str, str]] = {}
    for i, row in enumerate(rows, start=2):
        k = norm_key(row.get(key))
        if k is None:
            raise ConfigError(f"{path}: riga {i} senza '{key}'")
        if k in out:
            raise ConfigError(f"{path}: valore '{k}' ripetuto (riga {i})")
        out[k] = row
    return Lookup(name=name, path=path, key=key, rows=out)


def category_map(lookup: Lookup, column: str, allowed: dict[str, int]) -> dict[str, str]:
    """valore ER -> id categoria del modello, solo per le righe classificate.

    Una categoria che non esiste nel modello è un errore (niente correzioni silenziose).
    """
    out = {}
    for k, row in lookup.rows.items():
        cat = row.get(column, "")
        if not cat:
            continue
        if cat not in allowed:
            raise ConfigError(
                f"{lookup.path}: '{k}' -> {column}='{cat}' non è una categoria del modello "
                f"(ammesse: {', '.join(allowed)})"
            )
        out[k] = cat
    return out


def int_map(lookup: Lookup, column: str, max_value: int) -> dict[str, int]:
    """valore ER -> intero 0..max_value, solo per le righe con il campo compilato."""
    out = {}
    for k, row in lookup.rows.items():
        v = row.get(column, "")
        if v == "":
            continue
        try:
            n = int(v)
        except ValueError:
            raise ConfigError(f"{lookup.path}: '{k}' -> {column}='{v}' non è un intero") from None
        if not 0 <= n <= max_value:
            raise ConfigError(
                f"{lookup.path}: '{k}' -> {column}={n} fuori da 0..{max_value} (massimo remoto del modello)"
            )
        out[k] = n
    return out


def draft_count(lookup: Lookup) -> int:
    """Righe segnate come bozza (nota con "BOZZA"): il build lo scrive nel metadata."""
    return sum(1 for r in lookup.rows.values() if "bozza" in (r.get("note") or "").lower())
