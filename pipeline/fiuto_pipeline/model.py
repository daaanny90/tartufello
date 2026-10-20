"""Lettura del modello condiviso (model/vth-v1.json) e valutatore delle regole.

Le soglie stanno SOLO nel JSON del modello: qui non si duplica nessun numero.
Regole numeriche: lista ordinata, vince la prima che corrisponde. Chiavi
ammesse gt/gte/lt/lte (tutte in AND); una regola senza chiavi è il fallback.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .errors import ModelError
from .paths import REPO_ROOT

NA = 255  # "non disponibile" negli array di punti uint8

# I valori si arrotondano a 6 decimali prima del confronto: 7.2 salvato in
# float32 diventa 7.1999998 e senza arrotondare cadrebbe sotto la soglia.
# Non cambia nessuna soglia, toglie solo il rumore di rappresentazione.
DECIMALS = 6

MODEL_V1_PATH = REPO_ROOT / "model" / "vth-v1.json"
MODEL_V2_PATH = REPO_ROOT / "model" / "vth-v2.json"
DEFAULT_MODEL_PATH = MODEL_V2_PATH  # modello corrente; il build usa quello di build.toml

_OPS = {
    "gt": np.greater,
    "gte": np.greater_equal,
    "lt": np.less,
    "lte": np.less_equal,
}
_RULE_KEYS = set(_OPS) | {"points"}


def validate_rules(rules: list[dict], where: str = "") -> None:
    """Controlla che le regole usino solo chiavi note e abbiano i punti."""
    if not isinstance(rules, list) or not rules:
        raise ModelError(f"{where}: 'rules' deve essere una lista non vuota")
    for i, rule in enumerate(rules):
        unknown = set(rule) - _RULE_KEYS
        if unknown:
            raise ModelError(
                f"{where}: regola {i} con chiavi sconosciute {sorted(unknown)} "
                f"(ammesse: gt, gte, lt, lte, points)"
            )
        pts = rule.get("points")
        if not isinstance(pts, int) or isinstance(pts, bool) or not 0 <= pts < NA:
            raise ModelError(f"{where}: regola {i} senza 'points' intero valido")


def classify(values: np.ndarray, rules: list[dict]) -> np.ndarray:
    """Applica le regole ordinate (prima corrispondenza) a un array di valori.

    NaN = dato assente -> NA (255), anche se c'è una regola di fallback.
    Valori che non corrispondono a nessuna regola restano NA.
    """
    validate_rules(rules)
    vals = np.round(np.asarray(values, dtype="float64"), DECIMALS)
    out = np.full(vals.shape, NA, dtype="uint8")
    todo = np.isfinite(vals)
    for rule in rules:
        hit = todo.copy()
        for key, op in _OPS.items():
            if key in rule:
                hit &= op(vals, float(rule[key]))
        out[hit] = rule["points"]
        todo &= ~hit
        if not todo.any():
            break
    return out


def points_for(value: float | None, rules: list[dict]) -> int | None:
    """Versione scalare di `classify` (None se il valore manca)."""
    if value is None:
        return None
    p = int(classify(np.array([value], dtype="float64"), rules)[0])
    return None if p == NA else p


@dataclass
class Model:
    data: dict[str, Any]
    path: Path
    _params: dict[str, dict] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            self._params = {p["id"]: p for p in self.data["params"]}
            self.data["remote"]["minParams"]
            self.data["tiles"]["layer"]
        except (KeyError, TypeError) as exc:
            raise ModelError(f"{self.path}: struttura inattesa ({exc})") from exc
        for pid in self.remote_params():
            p = self._params[pid]
            if p.get("kind") == "numeric":
                validate_rules(p.get("rules"), where=f"{self.path.name} param {pid}")

    @property
    def id(self) -> str:
        return self.data["id"]

    @property
    def min_params(self) -> int:
        return int(self.data["remote"]["minParams"])

    @property
    def tile_layer(self) -> str:
        return self.data["tiles"]["layer"]

    @property
    def tile_properties(self) -> dict[str, str]:
        return self.data["tiles"]["properties"]

    def param(self, pid: str) -> dict:
        try:
            return self._params[pid]
        except KeyError:
            raise ModelError(f"parametro '{pid}' non presente nel modello {self.id}") from None

    def remote_params(self) -> list[str]:
        """Parametri calcolabili da remoto, nell'ordine del modello."""
        return [p["id"] for p in self.data["params"] if p.get("remote", {}).get("available")]

    def remote_max(self, pid: str) -> int:
        return int(self.param(pid)["remote"]["max"])

    def rules(self, pid: str) -> list[dict]:
        p = self.param(pid)
        if p.get("kind") != "numeric":
            raise ModelError(f"il parametro '{pid}' non è numerico")
        return p["rules"]

    def categories(self, pid: str) -> dict[str, int]:
        """id categoria -> punti (per i parametri di tipo 'category')."""
        p = self.param(pid)
        if p.get("kind") != "category":
            raise ModelError(f"il parametro '{pid}' non è a categorie")
        return {c["id"]: int(c["points"]) for c in p["categories"]}

    def classify(self, pid: str, values: np.ndarray) -> np.ndarray:
        return classify(values, self.rules(pid))


def load_model(path: str | Path | None = None) -> Model:
    p = Path(path) if path else DEFAULT_MODEL_PATH
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ModelError(f"modello non trovato: {p}") from None
    except json.JSONDecodeError as exc:
        raise ModelError(f"{p}: JSON non valido ({exc})") from exc
    return Model(data=data, path=p)
