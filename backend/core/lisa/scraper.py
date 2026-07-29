"""
backend/core/lisa/scraper.py
-----------------------------
Récupère les Objectifs Intermédiaires de Connaissance (OIC) depuis LiSA
via l'API MediaWiki (allpages + revisions).

Chaque OIC est une page-redirect nommée "OIC-{item}-{NN}-{rang}" pointant
vers la page dont le titre contient l'intitulé complet.
requests est déjà dans le projet.
"""
from __future__ import annotations

import re

from loguru import logger

from backend.config.settings import settings as _settings

try:
    import requests as _requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

_LISA_BASE = "https://livret.uness.fr/lisa/2026"
_LISA_API  = f"{_LISA_BASE}/api.php"

_OIC_CODE_RE = re.compile(r"OIC-(\d+)-(\d+)-([AB])$")
_REDIRECT_RE  = re.compile(r"#REDIRECT\s*\[\[(.+?)\s+(OIC-[^\]]+)\]\]", re.IGNORECASE)


class LisaFetchError(Exception):
    """Erreur réseau ou API lors du fetch LiSA."""

class _PermissionError(Exception):
    """Permission refusée par l'API MediaWiki (session expirée)."""


# ── Parsing réponse API ───────────────────────────────────────────────────────

def _parse_oic_api_pages(pages: dict) -> list[dict]:
    """
    Convertit les pages MediaWiki (dict pageid→pdata) en liste d'OIC.
    Chaque page est un redirect : #REDIRECT [[{intitulé} {OIC-code}]]
    """
    oics: list[dict] = []
    for pdata in pages.values():
        title = pdata.get("title", "")
        m_code = _OIC_CODE_RE.search(title)
        if not m_code:
            continue

        oic_code = title                    # e.g. "OIC-223-01-A"
        rang     = m_code.group(3)          # "A" or "B"
        ordre    = int(m_code.group(2))     # 1, 2, …

        content  = pdata.get("revisions", [{}])[0].get("*", "")
        m_redir  = _REDIRECT_RE.search(content)
        intitule = m_redir.group(1).strip() if m_redir else title

        oics.append({
            "oic_code": oic_code,
            "intitule": intitule,
            "rang":     rang,
            "rubrique": "",
            "ordre":    ordre,
        })

    oics.sort(key=lambda x: x["ordre"])
    return oics


# ── Fonction publique ─────────────────────────────────────────────────────────

def scrape_oic(course_title: str, item_number: str = "") -> list[dict]:
    """
    Scrappe les OIC d'un cours depuis LiSA via l'API MediaWiki.

    Retourne une liste de dicts (peut être vide).
    Lève LisaFetchError si erreur réseau ou API.
    """
    if not HAS_REQUESTS:
        raise LisaFetchError("requests non installé")

    if not item_number:
        logger.warning(f"LiSA scrape : item_number manquant pour {course_title!r}")
        return []

    try:
        item_int = int(item_number)
    except (ValueError, TypeError):
        logger.warning(f"LiSA scrape : item_number invalide {item_number!r}")
        return []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": "https://livret.uness.fr/lisa/2026/index.php",
    }
    if _settings.lisa_cookie:
        headers["Cookie"] = _settings.lisa_cookie

    params = {
        "action":     "query",
        "generator":  "allpages",
        # Les titres LiSA sont normalisés sur trois chiffres (OIC-095-01-A).
        "gapprefix":  f"OIC-{item_int:03d}-",
        "gaplimit":   "100",
        "prop":       "revisions",
        "rvprop":     "content",
        "format":     "json",
    }

    def _do_request(hdrs: dict) -> list[dict]:
        try:
            resp = _requests.get(_LISA_API, params=params, timeout=15, headers=hdrs)
            resp.raise_for_status()
        except Exception as exc:
            raise LisaFetchError(f"Erreur réseau LiSA : {exc}") from exc
        try:
            data = resp.json()
        except Exception as exc:
            raise LisaFetchError(f"Réponse LiSA non-JSON : {exc}") from exc
        if "error" in data:
            err  = data["error"]
            info = err.get("info", str(err))
            code = err.get("code", "")
            if code in ("readapidenied", "permissiondenied") or "permission" in info.lower():
                raise _PermissionError(info)
            raise LisaFetchError(f"API LiSA : {info}")
        pages = data.get("query", {}).get("pages", {})
        return _parse_oic_api_pages(pages)

    try:
        oics = _do_request(headers)
    except _PermissionError:
        # Session expirée → tenter un re-login automatique
        from backend.core.lisa.auth import auto_login
        new_cookie = auto_login()
        if new_cookie:
            new_headers = {**headers, "Cookie": new_cookie}
            try:
                oics = _do_request(new_headers)
            except _PermissionError as exc:
                raise LisaFetchError(f"API LiSA : {exc} (re-login échoué)") from exc
        else:
            raise LisaFetchError(
                "login_required: Session LiSA expirée. Configure tes identifiants UNESS dans Paramètres → LiSA."
            )

    logger.info(f"LiSA scrape '{course_title}' → {len(oics)} OIC")
    return oics
