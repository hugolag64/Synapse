"""
backend/core/lisa/scraper.py
-----------------------------
Récupère les Objectifs de Connaissance (OIC) depuis livret.uness.fr/lisa.

Utilise html.parser (stdlib) — aucune dépendance externe.
requests est déjà dans le projet.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import quote as _url_quote

from loguru import logger

try:
    import requests as _requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

_LISA_BASE = "https://livret.uness.fr/lisa/2026"


class LisaFetchError(Exception):
    """Erreur réseau ou timeout lors du fetch LiSA."""


# ── Parser HTML interne ───────────────────────────────────────────────────────

class _TableParser(HTMLParser):
    """Extrait toutes les lignes de tables HTML comme liste de listes de strings."""

    def __init__(self) -> None:
        super().__init__()
        self._in_cell = False
        self._cell_text = ""
        self._current_row: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("td", "th"):
            self._in_cell = True
            self._cell_text = ""
        elif tag == "tr":
            self._current_row = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th"):
            self._current_row.append(self._cell_text.strip())
            self._in_cell = False
        elif tag == "tr" and self._current_row:
            self.rows.append(self._current_row)
            self._current_row = []

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_text += data


# ── Extraction OIC ────────────────────────────────────────────────────────────

_OIC_CODE_RE = re.compile(r"(OIC-\d+-\d+-[AB])\s*$")


def _parse_oic_rows(rows: list[list[str]]) -> list[dict]:
    """
    Filtre les lignes de table dont la colonne Rang vaut "A" ou "B".
    Attendu : [Intitulé, Rang, Rubrique, Ordre]
    """
    oics: list[dict] = []
    for row in rows:
        if len(row) < 4:
            continue
        rang = row[1].strip()
        if rang not in ("A", "B"):
            continue
        intitule_full = row[0].strip()
        rubrique = row[2].strip()
        try:
            ordre = int(row[3].strip())
        except ValueError:
            ordre = 0

        # Extraire le code OIC (ex: "OIC-223-01-A") et nettoyer le titre
        m = _OIC_CODE_RE.search(intitule_full)
        oic_code = m.group(1) if m else ""
        intitule = _OIC_CODE_RE.sub("", intitule_full).strip()

        oics.append({
            "oic_code":  oic_code,
            "intitule":  intitule,
            "rang":      rang,
            "rubrique":  rubrique,
            "ordre":     ordre,
        })
    return oics


# ── Fonction publique ─────────────────────────────────────────────────────────

def scrape_oic(course_title: str, item_number: str = "") -> list[dict]:
    """
    Scrappe les OIC d'un cours depuis LiSA.

    Retourne une liste de dicts (peut être vide si page introuvable ou sans table).
    Lève LisaFetchError si erreur réseau/timeout.
    """
    if not HAS_REQUESTS:
        raise LisaFetchError("requests non installé")

    slug = _url_quote(course_title.replace(" ", "_"), safe="_-()")
    url = f"{_LISA_BASE}/{slug}"

    try:
        resp = _requests.get(url, timeout=10, headers={"User-Agent": "Synapse/1.0"})
    except Exception as exc:
        raise LisaFetchError(f"Erreur réseau LiSA : {exc}") from exc

    if resp.status_code == 404:
        logger.debug(f"LiSA 404 : {url}")
        return []

    try:
        resp.raise_for_status()
    except Exception as exc:
        raise LisaFetchError(f"LiSA HTTP {resp.status_code} : {exc}") from exc

    parser = _TableParser()
    parser.feed(resp.text)

    oics = _parse_oic_rows(parser.rows)
    logger.info(f"LiSA scrape '{course_title}' → {len(oics)} OIC")
    return oics
