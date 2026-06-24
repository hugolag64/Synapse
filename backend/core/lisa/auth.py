"""
backend/core/lisa/auth.py
--------------------------
Authentification automatique à LiSA via le CAS UNESS.
Suit le flow CAS standard : GET login → parse form → POST credentials → cookie.
"""
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

from loguru import logger

try:
    import requests as _requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from backend.config.settings import settings as _settings

_LISA_LOGIN = (
    "https://livret.uness.fr/lisa/2026/index.php"
    "?title=Sp%C3%A9cial:Connexion&returnto=Sp%C3%A9cial:Connexion"
)


class LisaAuthError(Exception):
    """Erreur lors de l'authentification LiSA/CAS."""


# ── Parseur de formulaire HTML ────────────────────────────────────────────────

class _FormParser(HTMLParser):
    """Extrait tous les formulaires d'une page, retourne celui avec un champ password."""

    def __init__(self) -> None:
        super().__init__()
        self._forms: list[dict] = []
        self._current: dict | None = None

    def handle_starttag(self, tag: str, attrs: list) -> None:
        a = dict(attrs)
        if tag == "form":
            self._current = {"action": a.get("action", ""), "fields": {}}
            self._forms.append(self._current)
        elif tag == "input" and self._current is not None:
            name = a.get("name")
            itype = a.get("type", "text").lower()
            if name and itype not in ("submit", "button", "image", "reset", "file"):
                self._current["fields"][name] = a.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._current = None

    def login_form(self) -> dict | None:
        """Retourne le formulaire contenant un champ 'password', ou le premier."""
        for form in self._forms:
            if "password" in form["fields"]:
                return form
        return self._forms[0] if self._forms else None


# ── Persistance .env ──────────────────────────────────────────────────────────

def _write_env(key: str, value: str) -> None:
    env_path = Path(".env")
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
        found = False
        for i, line in enumerate(lines):
            if line.lstrip().startswith(f"{key}=") or line.lstrip().startswith(f"{key} ="):
                lines[i] = f"{key}={value}"
                found = True
                break
        if not found:
            lines.append(f"{key}={value}")
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception as exc:
        logger.warning(f"Impossible d'écrire {key} dans .env : {exc}")


# ── Login CAS ─────────────────────────────────────────────────────────────────

def cas_login(username: str, password: str) -> str:
    """
    Authentifie l'utilisateur sur LiSA via le CAS UNESS.

    Retourne la chaîne cookie à injecter dans les requêtes API.
    Met à jour settings.lisa_cookie en mémoire et dans .env.
    Lève LisaAuthError en cas d'échec.
    """
    if not HAS_REQUESTS:
        raise LisaAuthError("requests non installé")
    if not username or not password:
        raise LisaAuthError("Identifiants UNESS manquants")

    session = _requests.Session()
    session.headers["User-Agent"] = "Synapse/1.0"

    # 1. GET LiSA login → suit la redirection vers le CAS
    try:
        r = session.get(_LISA_LOGIN, timeout=20, allow_redirects=True)
        r.raise_for_status()
    except Exception as exc:
        raise LisaAuthError(f"Impossible de joindre LiSA : {exc}") from exc

    cas_url = r.url  # URL finale après toutes les redirections (page CAS)

    # Si LiSA ne nous a pas redirigé vers CAS (session déjà valide ?)
    if "livret.uness.fr" in cas_url and "Connexion" not in cas_url:
        logger.info("LiSA : déjà authentifié ou wiki ouvert sans login")
        cookies = session.cookies.get_dict()
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        _settings.lisa_cookie = cookie_str
        _write_env("LISA_COOKIE", cookie_str)
        return cookie_str

    # 2. Parser le formulaire de login CAS
    parser = _FormParser()
    parser.feed(r.text)
    form = parser.login_form()

    if not form:
        raise LisaAuthError("Formulaire CAS introuvable — la structure du site a peut-être changé")

    form_data = form["fields"].copy()
    form_data["username"] = username
    form_data["password"] = password
    if "_eventId" not in form_data:
        form_data["_eventId"] = "submit"

    # Résoudre l'URL d'action (peut être relative)
    action = form["action"] or cas_url
    if action and not action.startswith("http"):
        parsed = urlparse(cas_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        action = urljoin(base, action)

    # 3. POST credentials → CAS redirige vers LiSA avec un ticket ST-xxx
    try:
        r2 = session.post(action, data=form_data, timeout=20, allow_redirects=True)
        r2.raise_for_status()
    except Exception as exc:
        raise LisaAuthError(f"Erreur lors du POST CAS : {exc}") from exc

    # 4. Vérifier qu'on a bien récupéré un cookie de session MediaWiki
    cookies = session.cookies.get_dict()
    if "mwdb_session" not in cookies:
        low = r2.text.lower()
        hint = ""
        if any(w in low for w in ("invalid", "incorrect", "erreur", "error", "bad credentials")):
            hint = " — identifiants incorrects ?"
        elif "captcha" in low:
            hint = " — captcha détecté (connexion manuelle requise)"
        raise LisaAuthError(f"Session LiSA non obtenue après login CAS{hint}")

    # 5. Construire la chaîne cookie, persister en mémoire et dans .env
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    _settings.lisa_cookie = cookie_str
    _write_env("LISA_COOKIE", cookie_str)
    logger.info("LiSA : authentification CAS réussie")
    return cookie_str


def auto_login() -> str | None:
    """
    Re-authentifie avec les credentials stockés si disponibles.
    Retourne le cookie ou None si aucun credentials configuré.
    """
    username = getattr(_settings, "lisa_username", "")
    password = getattr(_settings, "lisa_password", "")
    if not username or not password:
        return None
    try:
        return cas_login(username, password)
    except LisaAuthError as exc:
        logger.warning(f"auto_login LiSA échoué : {exc}")
        return None
