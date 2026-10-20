"""HTTP minimo con messaggi chiari. Usa i proxy e i certificati dell'ambiente."""

from __future__ import annotations

import re
import shutil
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

import requests

from .. import __version__
from ..errors import FiutoError

USER_AGENT = f"fiuto-pipeline/{__version__} (uso personale)"
TIMEOUT = (15, 120)  # connessione, lettura


def session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


RETRIES = 4  # tentativi in più dopo il primo
BACKOFF = 3.0  # secondi, raddoppia a ogni tentativo
RETRY_STATUS = {429, 500, 502, 503, 504}


def _sleep(seconds: float) -> None:  # separato per poterlo neutralizzare nei test
    time.sleep(seconds)


def get(sess: requests.Session, url: str, *, params=None, stream: bool = False) -> requests.Response:
    """GET con ritentativi: i server regionali a volte chiudono la connessione o rispondono 5xx."""
    last: Exception | None = None
    for attempt in range(RETRIES + 1):
        if attempt:
            _sleep(BACKOFF * 2 ** (attempt - 1))
        try:
            r = sess.get(url, params=params, timeout=TIMEOUT, stream=stream)
        except (requests.ConnectionError, requests.Timeout) as exc:
            last = exc
            continue
        except requests.RequestException as exc:
            last = exc
            break
        if r.status_code in RETRY_STATUS and attempt < RETRIES:
            last = FiutoError(f"HTTP {r.status_code} da {r.url}")
            r.close()
            continue
        if r.status_code >= 400:
            body = "" if stream else r.text[:300]
            raise FiutoError(f"HTTP {r.status_code} da {r.url}\n{body}")
        return r
    raise FiutoError(
        f"richiesta fallita verso {url} dopo {RETRIES + 1} tentativi: {last}\n"
        f"Controlla connessione/proxy; se l'host risponde dal browser, riprova."
    ) from last


def filename_from(resp: requests.Response, fallback: str) -> str:
    cd = resp.headers.get("Content-Disposition", "")
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?", cd)
    name = unquote(m.group(1)) if m else Path(unquote(urlsplit(resp.url).path)).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return name or fallback


def save_stream(resp: requests.Response, dest: Path) -> Path:
    """Scrive su .part e rinomina solo a fine download (niente file a metà in cache)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    resp.raw.decode_content = True  # gzip/deflate di trasporto
    with open(part, "wb") as f:
        shutil.copyfileobj(resp.raw, f, length=1 << 20)
    part.replace(dest)
    return dest


def looks_like_xml(path: Path) -> bool:
    """True se il file salvato è XML (tipico errore OGC al posto del dato)."""
    with open(path, "rb") as f:
        head = f.read(256).lstrip()
    return head.startswith(b"<")
