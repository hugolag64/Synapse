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

_LISA_HOME  = "https://livret.uness.fr/lisa/2026/index.php"
_LISA_API   = "https://livret.uness.fr/lisa/2026/api.php"


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

def _resolve_action(action: str, base_url: str) -> str:
    """Résout l'URL d'action d'un formulaire, relative au chemin courant (pas au domaine)."""
    if not action:
        return base_url
    if action.startswith("http"):
        return action
    return urljoin(base_url, action)


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
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    # 1. GET la page d'accueil LiSA (sans returnto) → redirige vers le CAS
    # Utiliser la page principale évite le problème de returnto=Spécial:Connexion
    # qui cause une boucle de redirection après login PluggableAuth.
    try:
        r = session.get(_LISA_HOME, timeout=20, allow_redirects=True)
        r.raise_for_status()
    except Exception as exc:
        raise LisaAuthError(f"Impossible de joindre LiSA : {exc}") from exc

    cas_url = r.url  # URL finale après toutes les redirections (page CAS)
    logger.debug(f"cas_login : URL après redirection = {cas_url}")

    # Si déjà sur LiSA → session SSO déjà active (fresh session unlikely, but handle it)
    if urlparse(cas_url).netloc == "livret.uness.fr":
        logger.info("LiSA : déjà sur LiSA sans redirection CAS")
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

    if "password" not in form["fields"]:
        # Le CAS UNESS utilise un flow "identifiant d'abord" : la 1ère page ne
        # contient qu'un champ username. La page renvoyée après soumission de
        # l'identifiant affiche le champ password avec un nouveau jeton
        # "execution". Injecter le password dans le 1er formulaire échoue
        # silencieusement (jeton invalide pour cette étape).
        step1_data = form["fields"].copy()
        step1_data["username"] = username
        action1 = _resolve_action(form["action"], cas_url)
        try:
            r_step1 = session.post(action1, data=step1_data, timeout=20, allow_redirects=True)
            r_step1.raise_for_status()
        except Exception as exc:
            raise LisaAuthError(f"Erreur lors de l'étape identifiant CAS : {exc}") from exc

        parser2 = _FormParser()
        parser2.feed(r_step1.text)
        form = parser2.login_form()
        if not form or "password" not in form["fields"]:
            raise LisaAuthError(
                "Formulaire de mot de passe CAS introuvable après l'étape identifiant "
                "— la structure du site a peut-être changé"
            )
        base_url = r_step1.url
    else:
        base_url = cas_url

    form_data = form["fields"].copy()
    form_data["username"] = username
    form_data["password"] = password
    if "_eventId" not in form_data:
        form_data["_eventId"] = "submit"

    # Résoudre l'URL d'action (peut être relative au chemin courant, pas juste au domaine)
    action = _resolve_action(form["action"], base_url)

    # 3. POST credentials → CAS redirige vers LiSA avec un ticket ST-xxx
    # Note : la chaîne de redirection OAuth2 termine parfois sur une URL cassée
    # côté UNESS (ex. "Index.php" au lieu de "index.php" → 404), alors que
    # l'authentification (et les cookies de session) a bien été établie avant
    # cette dernière étape. On ne lève donc pas sur un statut HTTP non-2xx ici ;
    # l'étape 4/5 vérifie l'état réel de la session.
    try:
        r2 = session.post(action, data=form_data, timeout=20, allow_redirects=True)
    except Exception as exc:
        raise LisaAuthError(f"Erreur lors du POST CAS : {exc}") from exc

    # 4. Vérifier que le CAS nous a bien redirigé vers LiSA
    final_url = r2.url
    cookies   = session.cookies.get_dict()
    on_lisa   = "livret.uness.fr" in final_url
    has_session = any("session" in k.lower() for k in cookies)

    if not on_lisa and not has_session:
        low  = r2.text.lower()
        hint = ""
        if any(w in low for w in ("invalid", "incorrect", "erreur", "error", "bad credentials", "mot de passe")):
            hint = " — identifiants incorrects ?"
        elif "captcha" in low:
            hint = " — captcha détecté (connexion manuelle requise)"
        logger.warning(f"cas_login : URL finale={final_url}, cookies={list(cookies)}")
        raise LisaAuthError(f"Authentification CAS échouée{hint}")

    # 5. Finaliser la session — visiter la page principale pour que
    #    PluggableAuth complète l'initialisation de la session MediaWiki.
    try:
        session.get(_LISA_HOME, timeout=15, allow_redirects=True)
    except Exception:
        pass

    cookies = session.cookies.get_dict()
    logger.info(f"LiSA CAS : cookies finaux — {list(cookies)}")

    # 6. Vérifier que la session est authentifiée (pas anonyme)
    try:
        whoami = session.get(
            _LISA_API,
            params={"action": "query", "meta": "userinfo", "format": "json"},
            timeout=10,
        )
        data = whoami.json()
        if "error" in data:
            code = data["error"].get("code", "")
            info = data["error"].get("info", "")
            logger.warning(f"LiSA : userinfo error code={code!r} — {info!r}")
            raise LisaAuthError(
                f"Session CAS obtenue mais API refuse (code={code!r}). "
                "Vérifiez vos identifiants UNESS."
            )
        uinfo   = data.get("query", {}).get("userinfo", {})
        is_anon = "anon" in uinfo
        uname   = uinfo.get("name", "?")
        if is_anon:
            logger.warning(f"LiSA : session anonyme après CAS login (cookies={list(cookies)})")
            raise LisaAuthError(
                "Authentification CAS réussie mais session MediaWiki anonyme. "
                "PluggableAuth n'a pas finalisé le login — vérifiez vos identifiants."
            )
        logger.info(f"LiSA : session authentifiée en tant que {uname!r}")
    except LisaAuthError:
        raise
    except Exception as exc:
        logger.debug(f"LiSA : impossible de vérifier userinfo ({exc}) — on continue")

    # 7. Persister le cookie en mémoire et dans .env
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
        logger.debug("auto_login LiSA : aucun credentials UNESS configurés (Paramètres → LiSA → Se connecter)")
        return None
    logger.info(f"auto_login LiSA : tentative de reconnexion pour {username!r}…")
    try:
        cookie = cas_login(username, password)
        logger.info("auto_login LiSA : reconnexion réussie")
        return cookie
    except LisaAuthError as exc:
        logger.warning(f"auto_login LiSA échoué : {exc}")
        return None
