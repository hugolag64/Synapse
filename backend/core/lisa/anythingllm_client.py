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


def _normalize(name: str) -> str:
    """Minuscule, sans accents ni emoji/symboles — ne garde que lettres/chiffres/espaces."""
    import re
    import unicodedata
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9 ]", "", ascii_only.lower()).strip()


def resolve_workspace_slug(college_name: str) -> str:
    """
    Résout le slug AnythingLLM correspondant à un collège Synapse.
    Compare à la fois le nom brut Notion et son équivalent COLLEGE_MAPPING
    (les workspaces peuvent être nommés selon l'une ou l'autre convention).
    Mise en cache mémoire après premier succès. Lève WorkspaceNotFoundError si aucun match.
    """
    if college_name in _workspace_slug_cache:
        return _workspace_slug_cache[college_name]

    from fuzzywuzzy import fuzz
    from backend.core.obsidian.service import COLLEGE_MAPPING

    candidate_names = {college_name, COLLEGE_MAPPING.get(college_name, college_name)}
    targets = [_normalize(name) for name in candidate_names]
    workspaces = list_workspaces()

    best_slug = None
    best_score = -1
    for ws in workspaces:
        candidate = _normalize(ws.get("name", ""))
        score = max(fuzz.token_sort_ratio(target, candidate) for target in targets)
        if score > best_score:
            best_score = score
            best_slug = ws.get("slug")

    if best_slug is None or best_score < WORKSPACE_MATCH_THRESHOLD:
        raise WorkspaceNotFoundError(
            f"Aucun workspace AnythingLLM ne correspond au collège « {college_name} »"
        )

    _workspace_slug_cache[college_name] = best_slug
    return best_slug


def clear_workspace_cache() -> None:
    """Vide le cache mémoire des slugs résolus (tests / rafraîchissement manuel)."""
    _workspace_slug_cache.clear()
