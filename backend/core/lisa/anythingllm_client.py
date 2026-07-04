"""Client HTTP fin pour l'API AnythingLLM (génération/correction des OIC)."""
from __future__ import annotations

try:
    import requests as _requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from backend.config.settings import settings as _settings

WORKSPACE_MATCH_THRESHOLD = 80  # fuzz.token_sort_ratio (0-100)

_workspace_slug_cache: dict[str, str] = {}


class AnythingLLMUnavailableError(Exception):
    """AnythingLLM est injoignable (serveur arrêté, mauvaise URL, timeout, réponse invalide)."""


class WorkspaceNotFoundError(Exception):
    """Aucun workspace AnythingLLM ne correspond au collège demandé."""


def _headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if _settings.anythingllm_api_key:
        headers["Authorization"] = f"Bearer {_settings.anythingllm_api_key}"
    return headers


def list_workspaces() -> list[dict]:
    """
    GET /api/v1/workspaces. Retourne la liste brute des workspaces.
    Lève AnythingLLMUnavailableError si injoignable ou réponse invalide.
    """
    if not HAS_REQUESTS:
        raise AnythingLLMUnavailableError("Le paquet 'requests' n'est pas installé")
    url = f"{_settings.anythingllm_url.rstrip('/')}/api/v1/workspaces"
    try:
        resp = _requests.get(url, headers=_headers(), timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        raise AnythingLLMUnavailableError(
            f"AnythingLLM inaccessible sur {_settings.anythingllm_url} : {exc}"
        ) from exc
    try:
        data = resp.json()
    except Exception as exc:
        raise AnythingLLMUnavailableError(f"Réponse AnythingLLM non-JSON : {exc}") from exc
    return data.get("workspaces", [])


def clear_workspace_cache() -> None:
    """Vide le cache mémoire des slugs résolus (tests / rafraîchissement manuel)."""
    _workspace_slug_cache.clear()
