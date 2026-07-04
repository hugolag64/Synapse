# Validation OIC via AnythingLLM — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformer chaque OIC LiSA en mini-quiz (QCM + questions ouvertes) généré et corrigé par AnythingLLM (grounded RAG sur les workspaces AnythingLLM existants, un par collège), avec progression de maîtrise 0→5 par OIC.

**Architecture:** Un client HTTP fin (`anythingllm_client.py`) parle à l'API AnythingLLM (`GET /api/v1/workspaces`, `POST /api/v1/workspace/{slug}/chat`). Un module de logique domaine (`evaluator.py`) construit les prompts, parse les réponses IA, et calcule le scoring/la progression — sans connaître les détails HTTP. Une nouvelle table SQLite `oic_attempts` + une colonne `oic_level` sur `lisa_oic` stockent l'historique et la progression. Une nouvelle dialog NiceGUI (`oic_eval_dialog.py`) fait passer le quiz question par question, branchée depuis `lisa_dialog.py`.

**Tech Stack:** Python 3.11, NiceGUI 3.8.0, SQLite (`sqlite3` stdlib), `requests` (HTTP sync), `fuzzywuzzy` (matching collège→workspace), pytest + `unittest.mock`.

## Global Constraints

- HTTP client : `requests` (sync), jamais `httpx`/`aiohttp` — convention du projet (voir `backend/core/lisa/scraper.py`).
- Appels bloquants depuis l'UI NiceGUI toujours enveloppés en `await asyncio.to_thread(...)` — jamais d'appel sync direct dans un handler `async def`.
- Toute nouvelle table/colonne SQLite passe par une migration idempotente dans `backend/core/reviews/local_store.py`, enregistrée dans `init_db()` — jamais de `ALTER TABLE` non gardé par une vérification `PRAGMA table_info`.
- Accès aux lignes SQLite via indexation `row["col"]`, jamais `.get()` (`sqlite3.Row` n'a pas de `.get()` — piège déjà rencontré dans ce fichier).
- Fuzzy matching : `fuzz.token_sort_ratio` de `fuzzywuzzy`, import différé dans la fonction, seuil en constante `UPPER_SNAKE` au niveau module — convention de `backend/core/ai_qcm/lacunes.py`.
- Le champ `mastered` (case à cocher manuelle) de `lisa_oic` reste indépendant de `oic_level` — ne jamais les coupler.
- Tests : `pytest` + `unittest.mock.patch` sur `"requests.get"`/`"requests.post"` — pas de librairie `responses`, pas de `monkeypatch` pour les mocks HTTP (seulement pour les settings/DB).
- Pas de test automatisé pour le rendu NiceGUI (aucun fichier `frontend/components/lisa_dialog.py` n'a de test dans ce projet) — les tâches UI se vérifient manuellement en lançant l'app.

---

## File Structure

| Fichier | Rôle |
|---|---|
| `backend/config/settings.py` | +2 champs : `anythingllm_url`, `anythingllm_api_key` |
| `requirements.txt`, `pyproject.toml` | +dépendance explicite `requests==2.32.4` (déjà installée en transitif, mais pas déclarée) |
| `backend/core/lisa/anythingllm_client.py` (nouveau) | Client HTTP fin : `list_workspaces`, `resolve_workspace_slug`, `query_workspace`, exceptions |
| `backend/core/reviews/local_store.py` | +migration `_migrate_oic_anythingllm_validation`, +colonne `oic_level`, +table `oic_attempts`, +3 fonctions CRUD |
| `backend/core/lisa/evaluator.py` (nouveau) | Logique domaine : dataclasses `Question`/`EvalResult`, génération/correction des questions, scoring, progression de niveau |
| `frontend/pages/settings.py` | +section "AnythingLLM" (URL, clé API, test de connexion) |
| `frontend/components/oic_eval_dialog.py` (nouveau) | Dialog quiz : génération, questions une par une, feedback, récapitulatif |
| `frontend/components/lisa_dialog.py` | +bouton "Évaluer" + badge de niveau par OIC dans `_render_oics` |
| `tests/test_anythingllm_client.py` (nouveau) | Tests du client HTTP |
| `tests/test_local_store.py` | +tests migration/CRUD `oic_attempts` |
| `tests/test_oic_evaluator.py` (nouveau) | Tests de la logique domaine |

---

### Task 1: Settings + client HTTP AnythingLLM — `list_workspaces`

**Files:**
- Modify: `backend/config/settings.py`
- Modify: `requirements.txt`, `pyproject.toml`
- Create: `backend/core/lisa/anythingllm_client.py`
- Test: `tests/test_anythingllm_client.py`

**Interfaces:**
- Produces: `anythingllm_client.AnythingLLMUnavailableError`, `anythingllm_client.list_workspaces() -> list[dict]`, `_settings.anythingllm_url: str`, `_settings.anythingllm_api_key: str`

- [ ] **Step 1: Ajouter les champs de settings**

Dans `backend/config/settings.py`, dans la classe `Settings`, juste après le champ `lisa_password` (dernier champ `lisa_*`) :

```python
    anythingllm_url: str = Field("http://localhost:3001", alias='ANYTHINGLLM_URL')
    anythingllm_api_key: str = Field("", alias='ANYTHINGLLM_API_KEY')
```

- [ ] **Step 2: Déclarer `requests` comme dépendance explicite**

Dans `requirements.txt`, ajouter après la ligne `python-Levenshtein==0.27.3` :

```
requests==2.32.4
```

Dans `pyproject.toml`, dans la liste `dependencies`, ajouter après `"python-Levenshtein==0.27.3",` :

```
    "requests==2.32.4",
```

- [ ] **Step 3: Écrire les tests (doivent échouer — le module n'existe pas encore)**

Créer `tests/test_anythingllm_client.py` :

```python
"""Tests unitaires — client HTTP AnythingLLM."""
import pytest
from unittest.mock import patch, MagicMock

from backend.core.lisa import anythingllm_client as client


@pytest.fixture(autouse=True)
def reset_cache():
    client.clear_workspace_cache()
    yield
    client.clear_workspace_cache()


def _mock_response(status_code: int, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        from requests import HTTPError
        resp.raise_for_status.side_effect = HTTPError(f"{status_code}")
    return resp


class TestListWorkspaces:
    def test_returns_workspace_list(self):
        payload = {"workspaces": [{"id": 1, "name": "Cardiologie", "slug": "cardiologie"}]}
        with patch("requests.get", return_value=_mock_response(200, payload)):
            result = client.list_workspaces()
        assert result == payload["workspaces"]

    def test_raises_on_connection_error(self):
        import requests
        with patch("requests.get", side_effect=requests.ConnectionError("refused")):
            with pytest.raises(client.AnythingLLMUnavailableError):
                client.list_workspaces()

    def test_raises_on_http_error(self):
        with patch("requests.get", return_value=_mock_response(500)):
            with pytest.raises(client.AnythingLLMUnavailableError):
                client.list_workspaces()

    def test_raises_on_non_json_response(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.side_effect = ValueError("not json")
        with patch("requests.get", return_value=resp):
            with pytest.raises(client.AnythingLLMUnavailableError):
                client.list_workspaces()

    def test_sends_bearer_header_when_api_key_set(self, monkeypatch):
        from backend.config.settings import settings
        monkeypatch.setattr(settings, "anythingllm_api_key", "secret-key")
        payload = {"workspaces": []}
        with patch("requests.get", return_value=_mock_response(200, payload)) as mock_get:
            client.list_workspaces()
        _, kwargs = mock_get.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer secret-key"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_anythingllm_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.core.lisa.anythingllm_client'`

- [ ] **Step 3: Implémenter le client HTTP (partie `list_workspaces`)**

Créer `backend/core/lisa/anythingllm_client.py` :

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_anythingllm_client.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/config/settings.py requirements.txt pyproject.toml backend/core/lisa/anythingllm_client.py tests/test_anythingllm_client.py
git commit -m "feat: add AnythingLLM client with list_workspaces"
```

---

### Task 2: Client AnythingLLM — `resolve_workspace_slug`

**Files:**
- Modify: `backend/core/lisa/anythingllm_client.py`
- Test: `tests/test_anythingllm_client.py`

**Interfaces:**
- Consumes: `list_workspaces() -> list[dict]` (Task 1), `_workspace_slug_cache: dict[str, str]` (Task 1)
- Produces: `resolve_workspace_slug(college_name: str) -> str`, `WorkspaceNotFoundError` (déjà défini Task 1)

- [ ] **Step 1: Écrire les tests (doivent échouer)**

Ajouter à `tests/test_anythingllm_client.py` :

```python
class TestResolveWorkspaceSlug:
    def test_matches_by_normalized_name(self):
        payload = {"workspaces": [
            {"id": 1, "name": "Cardiovasculaire", "slug": "cardiovasculaire-abcd"},
            {"id": 2, "name": "Dermatologie", "slug": "dermatologie-xyz"},
        ]}
        with patch("requests.get", return_value=_mock_response(200, payload)):
            slug = client.resolve_workspace_slug("Cardiovasculaire ❤️")
        assert slug == "cardiovasculaire-abcd"

    def test_caches_result_after_first_resolution(self):
        payload = {"workspaces": [{"id": 1, "name": "Cardiovasculaire", "slug": "cardio-slug"}]}
        with patch("requests.get", return_value=_mock_response(200, payload)) as mock_get:
            client.resolve_workspace_slug("Cardiovasculaire ❤️")
            client.resolve_workspace_slug("Cardiovasculaire ❤️")
        assert mock_get.call_count == 1

    def test_raises_when_no_match_above_threshold(self):
        payload = {"workspaces": [{"id": 1, "name": "Totalement autre chose", "slug": "autre"}]}
        with patch("requests.get", return_value=_mock_response(200, payload)):
            with pytest.raises(client.WorkspaceNotFoundError):
                client.resolve_workspace_slug("Cardiovasculaire ❤️")

    def test_raises_when_no_workspaces(self):
        payload = {"workspaces": []}
        with patch("requests.get", return_value=_mock_response(200, payload)):
            with pytest.raises(client.WorkspaceNotFoundError):
                client.resolve_workspace_slug("Cardiovasculaire ❤️")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_anythingllm_client.py::TestResolveWorkspaceSlug -v`
Expected: FAIL — `AttributeError: module 'backend.core.lisa.anythingllm_client' has no attribute 'resolve_workspace_slug'`

- [ ] **Step 3: Implémenter `resolve_workspace_slug`**

Ajouter à `backend/core/lisa/anythingllm_client.py`, avant `def clear_workspace_cache()` :

```python
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
    Mise en cache mémoire après premier succès. Lève WorkspaceNotFoundError si aucun match.
    """
    if college_name in _workspace_slug_cache:
        return _workspace_slug_cache[college_name]

    from fuzzywuzzy import fuzz

    target = _normalize(college_name)
    workspaces = list_workspaces()

    best_slug = None
    best_score = -1
    for ws in workspaces:
        candidate = _normalize(ws.get("name", ""))
        score = fuzz.token_sort_ratio(target, candidate)
        if score > best_score:
            best_score = score
            best_slug = ws.get("slug")

    if best_slug is None or best_score < WORKSPACE_MATCH_THRESHOLD:
        raise WorkspaceNotFoundError(
            f"Aucun workspace AnythingLLM ne correspond au collège « {college_name} »"
        )

    _workspace_slug_cache[college_name] = best_slug
    return best_slug
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_anythingllm_client.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/core/lisa/anythingllm_client.py tests/test_anythingllm_client.py
git commit -m "feat: resolve AnythingLLM workspace slug by fuzzy college name match"
```

---

### Task 3: Client AnythingLLM — `query_workspace`

**Files:**
- Modify: `backend/core/lisa/anythingllm_client.py`
- Test: `tests/test_anythingllm_client.py`

**Interfaces:**
- Produces: `query_workspace(slug: str, message: str) -> str`

- [ ] **Step 1: Écrire les tests (doivent échouer)**

Ajouter à `tests/test_anythingllm_client.py` :

```python
class TestQueryWorkspace:
    def test_returns_text_response(self):
        payload = {"id": "abc", "type": "textResponse", "textResponse": "Voici la réponse", "error": None}
        with patch("requests.post", return_value=_mock_response(200, payload)) as mock_post:
            result = client.query_workspace("cardio-slug", "Quelle question ?")
        assert result == "Voici la réponse"
        _, kwargs = mock_post.call_args
        assert kwargs["json"] == {"message": "Quelle question ?", "mode": "query"}

    def test_raises_on_connection_error(self):
        import requests
        with patch("requests.post", side_effect=requests.ConnectionError("refused")):
            with pytest.raises(client.AnythingLLMUnavailableError):
                client.query_workspace("cardio-slug", "msg")

    def test_raises_when_api_returns_error_field(self):
        payload = {"textResponse": None, "error": "workspace not found"}
        with patch("requests.post", return_value=_mock_response(200, payload)):
            with pytest.raises(client.AnythingLLMUnavailableError):
                client.query_workspace("cardio-slug", "msg")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_anythingllm_client.py::TestQueryWorkspace -v`
Expected: FAIL — `AttributeError: module 'backend.core.lisa.anythingllm_client' has no attribute 'query_workspace'`

- [ ] **Step 3: Implémenter `query_workspace`**

Ajouter à `backend/core/lisa/anythingllm_client.py`, après `list_workspaces` et avant `_normalize` :

```python
def query_workspace(slug: str, message: str) -> str:
    """
    POST /api/v1/workspace/{slug}/chat, mode='query'. Timeout 45s.
    Retourne le texte brut de la réponse (champ 'textResponse').
    """
    if not HAS_REQUESTS:
        raise AnythingLLMUnavailableError("Le paquet 'requests' n'est pas installé")
    url = f"{_settings.anythingllm_url.rstrip('/')}/api/v1/workspace/{slug}/chat"
    try:
        resp = _requests.post(
            url,
            headers=_headers(),
            json={"message": message, "mode": "query"},
            timeout=45,
        )
        resp.raise_for_status()
    except Exception as exc:
        raise AnythingLLMUnavailableError(
            f"AnythingLLM inaccessible sur {_settings.anythingllm_url} : {exc}"
        ) from exc
    try:
        data = resp.json()
    except Exception as exc:
        raise AnythingLLMUnavailableError(f"Réponse AnythingLLM non-JSON : {exc}") from exc
    if data.get("error"):
        raise AnythingLLMUnavailableError(f"Erreur AnythingLLM : {data['error']}")
    return data.get("textResponse", "")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_anythingllm_client.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/core/lisa/anythingllm_client.py tests/test_anythingllm_client.py
git commit -m "feat: add AnythingLLM query_workspace chat call"
```

---

### Task 4: SQLite — migration `oic_level`/`oic_attempts` + CRUD

**Files:**
- Modify: `backend/core/reviews/local_store.py`
- Test: `tests/test_local_store.py`

**Interfaces:**
- Produces: `save_oic_attempt(oic_id: int, session_score: int, questions_json: str) -> int`, `get_oic_attempts(oic_id: int, limit: int = 10) -> list[sqlite3.Row]`, `update_oic_level(oic_id: int, new_level: int) -> None`, colonne `lisa_oic.oic_level` (INTEGER, défaut 0), table `oic_attempts`

- [ ] **Step 1: Écrire les tests (doivent échouer)**

Ajouter à la fin de `tests/test_local_store.py` :

```python
class TestMigrateOicAnythingLLM:
    def test_adds_oic_level_column(self):
        cols = {row["name"] for row in ls._conn().execute("PRAGMA table_info(lisa_oic)").fetchall()}
        assert "oic_level" in cols

    def test_creates_oic_attempts_table(self):
        tables = {row["name"] for row in ls._conn().execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "oic_attempts" in tables

    def test_migration_idempotent(self):
        ls._migrate_oic_anythingllm_validation()
        ls._migrate_oic_anythingllm_validation()
        cols = [row["name"] for row in ls._conn().execute("PRAGMA table_info(lisa_oic)").fetchall()]
        assert cols.count("oic_level") == 1


class TestOicAttempts:
    def _make_oic(self) -> int:
        ls.upsert_lisa_oic("course-1", [
            {"oic_code": "OIC-001", "intitule": "Test OIC", "rang": "A"},
        ])
        row = ls._conn().execute(
            "SELECT id FROM lisa_oic WHERE course_id = ?", ("course-1",)
        ).fetchone()
        return row["id"]

    def test_save_oic_attempt_returns_id(self):
        oic_id = self._make_oic()
        attempt_id = ls.save_oic_attempt(oic_id, 85, '[{"enonce": "q1"}]')
        assert attempt_id > 0

    def test_get_oic_attempts_returns_most_recent_first(self):
        oic_id = self._make_oic()
        ls.save_oic_attempt(oic_id, 40, "[]")
        ls.save_oic_attempt(oic_id, 90, "[]")
        attempts = ls.get_oic_attempts(oic_id)
        assert [a["session_score"] for a in attempts] == [90, 40]

    def test_get_oic_attempts_respects_limit(self):
        oic_id = self._make_oic()
        for score in (10, 20, 30, 40):
            ls.save_oic_attempt(oic_id, score, "[]")
        attempts = ls.get_oic_attempts(oic_id, limit=2)
        assert [a["session_score"] for a in attempts] == [40, 30]

    def test_update_oic_level(self):
        oic_id = self._make_oic()
        ls.update_oic_level(oic_id, 3)
        row = ls._conn().execute("SELECT oic_level FROM lisa_oic WHERE id = ?", (oic_id,)).fetchone()
        assert row["oic_level"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_store.py::TestMigrateOicAnythingLLM tests/test_local_store.py::TestOicAttempts -v`
Expected: FAIL — `sqlite3.OperationalError: no such column: oic_level` / `AttributeError: module has no attribute 'save_oic_attempt'`

- [ ] **Step 3: Implémenter la migration et le CRUD**

Dans `backend/core/reviews/local_store.py`, ajouter la fonction de migration juste avant `_migrate_routine_tables` (ou n'importe où parmi les autres `_migrate_*`, à condition de l'enregistrer dans `init_db()`) :

```python
def _migrate_oic_anythingllm_validation() -> None:
    """
    Migration douce : ajoute oic_level à lisa_oic et crée oic_attempts.
    Idempotente — ne touche pas aux données existantes.
    """
    with _conn() as con:
        existing = {
            row["name"]
            for row in con.execute("PRAGMA table_info(lisa_oic)").fetchall()
        }
        if "oic_level" not in existing:
            con.execute("ALTER TABLE lisa_oic ADD COLUMN oic_level INTEGER NOT NULL DEFAULT 0")
        con.executescript("""
            CREATE TABLE IF NOT EXISTS oic_attempts (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                oic_id         INTEGER NOT NULL REFERENCES lisa_oic(id),
                session_score  INTEGER NOT NULL,
                questions_json TEXT    NOT NULL,
                attempted_at   TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_oic_attempts_oic ON oic_attempts(oic_id);
        """)
```

Dans `init_db()`, ajouter l'appel à la fin de la chaîne de migrations (juste après `_migrate_routine_tables()`) :

```python
    _migrate_routine_tables()
    _migrate_oic_anythingllm_validation()
```

Ajouter les 3 fonctions CRUD juste après `toggle_lisa_oic_mastery` :

```python
def save_oic_attempt(oic_id: int, session_score: int, questions_json: str) -> int:
    """Enregistre une tentative d'évaluation OIC. Retourne l'id inséré."""
    with _conn() as con:
        cur = con.execute(
            """INSERT INTO oic_attempts (oic_id, session_score, questions_json, attempted_at)
               VALUES (?, ?, ?, ?)""",
            (oic_id, session_score, questions_json, _now()),
        )
        return cur.lastrowid


def get_oic_attempts(oic_id: int, limit: int = 10) -> list:
    """Retourne les tentatives d'un OIC, les plus récentes en premier."""
    with _conn() as con:
        return con.execute(
            "SELECT * FROM oic_attempts WHERE oic_id = ? ORDER BY id DESC LIMIT ?",
            (oic_id, limit),
        ).fetchall()


def update_oic_level(oic_id: int, new_level: int) -> None:
    """Met à jour le niveau de maîtrise progressif d'un OIC."""
    with _conn() as con:
        con.execute("UPDATE lisa_oic SET oic_level = ? WHERE id = ?", (new_level, oic_id))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_store.py -v`
Expected: PASS (tous les tests existants + les nouveaux)

- [ ] **Step 5: Commit**

```bash
git add backend/core/reviews/local_store.py tests/test_local_store.py
git commit -m "feat: add oic_level column and oic_attempts table with CRUD"
```

---

### Task 5: Evaluator — dataclasses + scoring pur (`grade_qcm`, `aggregate_session_score`, `next_oic_level`)

**Files:**
- Create: `backend/core/lisa/evaluator.py`
- Test: `tests/test_oic_evaluator.py`

**Interfaces:**
- Produces: `Question` (dataclass: `type: Literal["qcm","ouverte"]`, `enonce: str`, `options: list[str]|None`, `correct_index: int|None`, `explication: str|None`, `criteres: list[str]|None`), `EvalResult` (dataclass: `verdict: Literal["correct","partial","incorrect"]`, `score: int`, `elements_corrects: list[str]`, `elements_manquants: list[str]`, `explication: str`, `rappel_cours: str`), `grade_qcm(question: Question, selected_index: int) -> EvalResult`, `aggregate_session_score(results: list[EvalResult]) -> int`, `next_oic_level(current_level: int, session_score: int, previous_scores: list[int]) -> int`

- [ ] **Step 1: Écrire les tests (doivent échouer — le module n'existe pas)**

Créer `tests/test_oic_evaluator.py` :

```python
"""Tests unitaires — évaluateur OIC (logique pure + AnythingLLM)."""
import pytest
from unittest.mock import patch

from backend.core.lisa import evaluator


class TestGradeQcm:
    def test_correct_answer(self):
        q = evaluator.Question(type="qcm", enonce="?", options=["a", "b"], correct_index=1, explication="car b")
        result = evaluator.grade_qcm(q, 1)
        assert result.verdict == "correct"
        assert result.score == 100
        assert result.explication == "car b"

    def test_incorrect_answer(self):
        q = evaluator.Question(type="qcm", enonce="?", options=["a", "b"], correct_index=1, explication="car b")
        result = evaluator.grade_qcm(q, 0)
        assert result.verdict == "incorrect"
        assert result.score == 0


class TestAggregateSessionScore:
    def test_averages_scores(self):
        results = [
            evaluator.EvalResult(verdict="correct", score=100),
            evaluator.EvalResult(verdict="incorrect", score=0),
        ]
        assert evaluator.aggregate_session_score(results) == 50

    def test_empty_list_returns_zero(self):
        assert evaluator.aggregate_session_score([]) == 0

    def test_rounds_to_nearest_int(self):
        results = [
            evaluator.EvalResult(verdict="correct", score=100),
            evaluator.EvalResult(verdict="correct", score=100),
            evaluator.EvalResult(verdict="incorrect", score=0),
        ]
        assert evaluator.aggregate_session_score(results) == 67


class TestNextOicLevel:
    def test_increments_on_high_score(self):
        assert evaluator.next_oic_level(2, 85, []) == 3

    def test_caps_at_five_only_with_two_prior_high_scores(self):
        assert evaluator.next_oic_level(4, 85, [90, 88]) == 5

    def test_caps_at_four_without_enough_history(self):
        assert evaluator.next_oic_level(4, 85, [90]) == 4

    def test_caps_at_four_when_prior_score_low(self):
        assert evaluator.next_oic_level(4, 85, [90, 40]) == 4

    def test_stays_same_on_partial_score_above_level_three(self):
        assert evaluator.next_oic_level(3, 60, []) == 3

    def test_decrements_on_partial_score_below_level_three(self):
        assert evaluator.next_oic_level(2, 60, []) == 1

    def test_decrements_on_low_score(self):
        assert evaluator.next_oic_level(3, 30, []) == 2

    def test_never_drops_below_zero(self):
        assert evaluator.next_oic_level(0, 20, []) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_oic_evaluator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.core.lisa.evaluator'`

- [ ] **Step 3: Implémenter les dataclasses et fonctions pures**

Créer `backend/core/lisa/evaluator.py` :

```python
"""Logique domaine : génération/correction des questions OIC via AnythingLLM."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal

from backend.core.lisa import anythingllm_client as _client


@dataclass
class Question:
    type: Literal["qcm", "ouverte"]
    enonce: str
    options: list[str] | None = None
    correct_index: int | None = None
    explication: str | None = None    # QCM uniquement, caché de l'UI jusqu'à réponse
    criteres: list[str] | None = None  # ouverte uniquement, caché de l'UI jusqu'à réponse


@dataclass
class EvalResult:
    verdict: Literal["correct", "partial", "incorrect"]
    score: int
    elements_corrects: list[str] = field(default_factory=list)
    elements_manquants: list[str] = field(default_factory=list)
    explication: str = ""
    rappel_cours: str = ""


def grade_qcm(question: Question, selected_index: int) -> EvalResult:
    """Correction locale instantanée d'une question QCM, pas d'appel réseau."""
    is_correct = selected_index == question.correct_index
    return EvalResult(
        verdict="correct" if is_correct else "incorrect",
        score=100 if is_correct else 0,
        explication=question.explication or "",
    )


def aggregate_session_score(results: list[EvalResult]) -> int:
    """Moyenne arrondie des scores par question de la session, 0-100."""
    if not results:
        return 0
    return round(sum(r.score for r in results) / len(results))


def next_oic_level(current_level: int, session_score: int, previous_scores: list[int]) -> int:
    """
    Fait évoluer le niveau de maîtrise (0-5) selon le score de la session courante.
    `previous_scores` : scores des 2 tentatives précédentes les plus récentes
    (plus récente en premier), utilisés uniquement pour confirmer le niveau 5
    (exige 3 tentatives consécutives >= 80%, celle-ci incluse).
    """
    if session_score >= 80:
        provisional = min(5, current_level + 1)
    elif session_score >= 50:
        provisional = current_level if current_level >= 3 else max(0, current_level - 1)
    else:
        provisional = max(0, current_level - 1)

    if provisional == 5:
        last_two = previous_scores[:2]
        if len(last_two) < 2 or any(s < 80 for s in last_two):
            provisional = 4

    return provisional
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_oic_evaluator.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/core/lisa/evaluator.py tests/test_oic_evaluator.py
git commit -m "feat: add OIC scoring logic (grade_qcm, session score, level progression)"
```

---

### Task 6: Evaluator — `generate_questions`

**Files:**
- Modify: `backend/core/lisa/evaluator.py`
- Test: `tests/test_oic_evaluator.py`

**Interfaces:**
- Consumes: `_client.query_workspace(slug: str, message: str) -> str` (Task 3), `Question` (Task 5)
- Produces: `generate_questions(course_title: str, intitule: str, rang: str, workspace_slug: str) -> list[Question]`

- [ ] **Step 1: Écrire les tests (doivent échouer)**

Ajouter à `tests/test_oic_evaluator.py` :

```python
class TestGenerateQuestions:
    def test_parses_valid_json_response(self):
        raw = (
            '[{"type": "qcm", "enonce": "Q1?", "options": ["a", "b"], "correct_index": 0, "explication": "exp"},'
            '{"type": "ouverte", "enonce": "Q2?", "criteres": ["c1", "c2"]}]'
        )
        with patch("backend.core.lisa.evaluator._client.query_workspace", return_value=raw):
            questions = evaluator.generate_questions("ITEM 1 - Cours", "Intitulé", "A", "slug")
        assert len(questions) == 2
        assert questions[0].type == "qcm"
        assert questions[0].correct_index == 0
        assert questions[1].type == "ouverte"
        assert questions[1].criteres == ["c1", "c2"]

    def test_extracts_json_surrounded_by_text(self):
        raw = 'Voici le résultat :\n[{"type": "ouverte", "enonce": "Q?", "criteres": ["c"]}]\nMerci.'
        with patch("backend.core.lisa.evaluator._client.query_workspace", return_value=raw):
            questions = evaluator.generate_questions("Cours", "Intitulé", "A", "slug")
        assert len(questions) == 1
        assert questions[0].enonce == "Q?"

    def test_retries_once_on_invalid_json_then_succeeds(self):
        responses = ["pas du json", '[{"type": "ouverte", "enonce": "Q?", "criteres": ["c"]}]']
        with patch("backend.core.lisa.evaluator._client.query_workspace", side_effect=responses) as mock_q:
            questions = evaluator.generate_questions("Cours", "Intitulé", "A", "slug")
        assert mock_q.call_count == 2
        assert len(questions) == 1

    def test_falls_back_to_generic_question_after_two_failures(self):
        with patch("backend.core.lisa.evaluator._client.query_workspace", return_value="pas du json du tout"):
            questions = evaluator.generate_questions("Cours", "Mon Intitulé", "A", "slug")
        assert len(questions) == 1
        assert questions[0].type == "ouverte"
        assert "Mon Intitulé" in questions[0].enonce
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_oic_evaluator.py::TestGenerateQuestions -v`
Expected: FAIL — `AttributeError: module 'backend.core.lisa.evaluator' has no attribute 'generate_questions'`

- [ ] **Step 3: Implémenter `generate_questions`**

Ajouter à `backend/core/lisa/evaluator.py`, à la fin du fichier :

```python
def _extract_json(raw: str):
    try:
        return json.loads(raw)
    except Exception:
        pass
    match = re.search(r"[\[{].*[\]}]", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return None


def generate_questions(course_title: str, intitule: str, rang: str, workspace_slug: str) -> list[Question]:
    """
    Appel query #1. Demande 3-5 questions mixtes QCM/ouvertes en JSON strict.
    Retry une fois si JSON invalide. Dégradé : une question ouverte générique si échec double.
    """
    prompt = (
        "Tu es un enseignant en médecine française (EDN/ECN).\n"
        f'Cours : "{course_title}"\n'
        f'OIC (Objectif Intermédiaire de Connaissance) : "{intitule}"\n'
        f"Rang : {rang}\n\n"
        "En te basant sur les documents de ce workspace concernant ce cours,\n"
        "génère entre 3 et 5 questions pour tester la maîtrise de cet OIC,\n"
        "en mélangeant QCM et questions ouvertes.\n\n"
        "Réponds UNIQUEMENT avec ce JSON (pas de texte autour) :\n"
        "[\n"
        '  {"type": "qcm", "enonce": "...", "options": ["...", "...", "..."], "correct_index": 0, "explication": "..."},\n'
        '  {"type": "ouverte", "enonce": "...", "criteres": ["critère 1", "critère 2"]}\n'
        "]"
    )

    for _attempt in range(2):
        raw = _client.query_workspace(workspace_slug, prompt)
        parsed = _extract_json(raw)
        if isinstance(parsed, list) and parsed:
            questions = []
            for item in parsed:
                q_type = item.get("type")
                if q_type not in ("qcm", "ouverte"):
                    continue
                questions.append(Question(
                    type=q_type,
                    enonce=item.get("enonce", ""),
                    options=item.get("options"),
                    correct_index=item.get("correct_index"),
                    explication=item.get("explication"),
                    criteres=item.get("criteres"),
                ))
            if questions:
                return questions

    return [Question(type="ouverte", enonce=f"Expliquez : {intitule}", criteres=[f"Connaître {intitule}"])]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_oic_evaluator.py -v`
Expected: PASS (14 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/core/lisa/evaluator.py tests/test_oic_evaluator.py
git commit -m "feat: generate mixed QCM/open questions for an OIC via AnythingLLM"
```

---

### Task 7: Evaluator — `evaluate_open_answer`

**Files:**
- Modify: `backend/core/lisa/evaluator.py`
- Test: `tests/test_oic_evaluator.py`

**Interfaces:**
- Consumes: `_client.query_workspace` (Task 3), `Question`, `EvalResult`, `_extract_json` (Task 5/6)
- Produces: `evaluate_open_answer(question: Question, student_response: str, workspace_slug: str) -> EvalResult`

- [ ] **Step 1: Écrire les tests (doivent échouer)**

Ajouter à `tests/test_oic_evaluator.py` :

```python
class TestEvaluateOpenAnswer:
    def test_parses_valid_json_response(self):
        raw = (
            '{"verdict": "partial", "score": 65, "elements_corrects": ["a"], '
            '"elements_manquants": ["b"], "explication": "exp", "rappel_cours": "rappel"}'
        )
        q = evaluator.Question(type="ouverte", enonce="Q?", criteres=["a", "b"])
        with patch("backend.core.lisa.evaluator._client.query_workspace", return_value=raw):
            result = evaluator.evaluate_open_answer(q, "ma réponse", "slug")
        assert result.verdict == "partial"
        assert result.score == 65
        assert result.elements_manquants == ["b"]

    def test_retries_once_on_invalid_json_then_succeeds(self):
        responses = ["texte invalide", '{"verdict": "correct", "score": 90}']
        q = evaluator.Question(type="ouverte", enonce="Q?", criteres=["a"])
        with patch("backend.core.lisa.evaluator._client.query_workspace", side_effect=responses) as mock_q:
            result = evaluator.evaluate_open_answer(q, "réponse", "slug")
        assert mock_q.call_count == 2
        assert result.verdict == "correct"

    def test_falls_back_to_incorrect_after_two_failures(self):
        q = evaluator.Question(type="ouverte", enonce="Q?", criteres=["a"])
        with patch("backend.core.lisa.evaluator._client.query_workspace", return_value="pas du json"):
            result = evaluator.evaluate_open_answer(q, "réponse", "slug")
        assert result.verdict == "incorrect"
        assert result.score == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_oic_evaluator.py::TestEvaluateOpenAnswer -v`
Expected: FAIL — `AttributeError: module 'backend.core.lisa.evaluator' has no attribute 'evaluate_open_answer'`

- [ ] **Step 3: Implémenter `evaluate_open_answer`**

Ajouter à `backend/core/lisa/evaluator.py`, à la fin du fichier :

```python
def evaluate_open_answer(question: Question, student_response: str, workspace_slug: str) -> EvalResult:
    """Appel query #2, un par question ouverte répondue. Retry une fois si JSON invalide."""
    criteres = question.criteres or []
    prompt = (
        "Tu es un correcteur médical pour l'EDN (Examen Classant National).\n"
        "Base-toi sur les documents de ce workspace pour vérifier l'exactitude.\n\n"
        f'Question : "{question.enonce}"\n'
        f"Critères attendus : {json.dumps(criteres, ensure_ascii=False)}\n"
        f'Réponse de l\'étudiant : "{student_response}"\n\n'
        "Évalue si la réponse couvre les critères attendus.\n"
        "Réponds UNIQUEMENT avec ce JSON (pas de texte autour) :\n"
        "{\n"
        '  "verdict": "correct" | "partial" | "incorrect",\n'
        '  "score": <entier 0-100>,\n'
        '  "elements_corrects": ["..."],\n'
        '  "elements_manquants": ["..."],\n'
        '  "explication": "<phrase courte>",\n'
        '  "rappel_cours": "<rappel essentiel en 1-3 phrases>"\n'
        "}"
    )

    for _attempt in range(2):
        raw = _client.query_workspace(workspace_slug, prompt)
        parsed = _extract_json(raw)
        if isinstance(parsed, dict) and "verdict" in parsed and "score" in parsed:
            return EvalResult(
                verdict=parsed.get("verdict", "incorrect"),
                score=int(parsed.get("score", 0)),
                elements_corrects=parsed.get("elements_corrects", []),
                elements_manquants=parsed.get("elements_manquants", []),
                explication=parsed.get("explication", ""),
                rappel_cours=parsed.get("rappel_cours", ""),
            )

    return EvalResult(verdict="incorrect", score=0, explication="Erreur de parsing IA")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_oic_evaluator.py -v`
Expected: PASS (17 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/core/lisa/evaluator.py tests/test_oic_evaluator.py
git commit -m "feat: evaluate open-ended OIC answers via AnythingLLM"
```

---

### Task 8: Settings UI — section "AnythingLLM"

**Files:**
- Modify: `frontend/pages/settings.py`

**Interfaces:**
- Consumes: `_app_settings.anythingllm_url`, `_app_settings.anythingllm_api_key` (Task 1), `_write_env_var(key, value) -> bool` (existant, ligne 736), `anythingllm_client.list_workspaces` + `AnythingLLMUnavailableError` (Task 1)

Pas de test automatisé — aucune section de `settings.py` n'a de test dans ce projet (vérification manuelle en Task 11).

- [ ] **Step 1: Ajouter la section "AnythingLLM"**

Dans `frontend/pages/settings.py`, insérer juste après la ligne 370 (`ui.button('Sauvegarder cookie', ...)`) et juste avant le commentaire `# Agendas Google Calendar` (ligne 372) :

```python

        # AnythingLLM
        with ui.expansion('AnythingLLM', icon='smart_toy').classes(
            'w-full rounded-xl border border-indigo-200 dark:border-indigo-800 mb-3 shadow-sm'
        ).props('header-class="font-semibold text-indigo-700 dark:text-indigo-300"'):
            with ui.column().classes('p-4 w-full gap-4'):
                with ui.row().classes('items-start gap-2 p-3 bg-indigo-50 dark:bg-indigo-900/20 rounded-xl border border-indigo-100 dark:border-indigo-800'):
                    ui.icon('auto_awesome', color='indigo').classes('text-lg shrink-0 mt-0.5')
                    with ui.column().classes('gap-0.5'):
                        ui.label('Évaluation des OIC par IA locale').classes('text-xs text-indigo-700 dark:text-indigo-300 font-semibold')
                        ui.label('AnythingLLM doit tourner en local avec un workspace par collège.').classes('text-xs text-slate-500')
                anythingllm_url_input = ui.input(
                    label='URL AnythingLLM',
                    value=_app_settings.anythingllm_url,
                    placeholder='http://localhost:3001',
                ).props('outlined').classes('w-full')
                anythingllm_key_input = ui.input(
                    label='Clé API',
                    value=_app_settings.anythingllm_api_key,
                    password=True, password_toggle_button=True,
                ).props('outlined').classes('w-full')
                anythingllm_status = ui.label('').classes('text-xs text-slate-400 -mt-1')

                async def _test_anythingllm():
                    import asyncio
                    url = (anythingllm_url_input.value or '').strip()
                    key = (anythingllm_key_input.value or '').strip()
                    _write_env_var('ANYTHINGLLM_URL', url)
                    _write_env_var('ANYTHINGLLM_API_KEY', key)
                    _app_settings.anythingllm_url = url
                    _app_settings.anythingllm_api_key = key
                    anythingllm_status.set_text('Connexion en cours…')
                    anythingllm_status.classes('text-slate-400', remove='text-emerald-600 text-red-500')
                    try:
                        from backend.core.lisa.anythingllm_client import list_workspaces, AnythingLLMUnavailableError
                        workspaces = await asyncio.to_thread(list_workspaces)
                        anythingllm_status.set_text(f'Connecté ✓ — {len(workspaces)} workspace(s) trouvé(s)')
                        anythingllm_status.classes('text-emerald-600', remove='text-slate-400 text-red-500')
                        ui.notify('Connexion AnythingLLM réussie ✓', type='positive', icon='smart_toy')
                    except AnythingLLMUnavailableError as exc:
                        anythingllm_status.set_text(f'Échec : {exc}')
                        anythingllm_status.classes('text-red-500', remove='text-slate-400 text-emerald-600')
                        ui.notify(str(exc), type='negative')

                ui.button('Tester la connexion', icon='wifi', on_click=_test_anythingllm).props('unelevated color=indigo size=sm rounded')
```

- [ ] **Step 2: Vérifier que l'app démarre sans erreur**

Run: `python -c "import ast; ast.parse(open('frontend/pages/settings.py', encoding='utf-8').read())"`
Expected: pas d'exception (syntaxe valide)

- [ ] **Step 3: Commit**

```bash
git add frontend/pages/settings.py
git commit -m "feat: add AnythingLLM settings section with connection test"
```

---

### Task 9: Dialog quiz — `oic_eval_dialog.py`

**Files:**
- Create: `frontend/components/oic_eval_dialog.py`

**Interfaces:**
- Consumes: `evaluator.Question`, `evaluator.EvalResult`, `evaluator.generate_questions`, `evaluator.evaluate_open_answer`, `evaluator.grade_qcm`, `evaluator.aggregate_session_score`, `evaluator.next_oic_level` (Tasks 5-7), `anythingllm_client.resolve_workspace_slug`, `AnythingLLMUnavailableError`, `WorkspaceNotFoundError` (Tasks 1-2), `local_store.save_oic_attempt`, `local_store.get_oic_attempts`, `local_store.update_oic_level` (Task 4), `oic: sqlite3.Row` (colonnes `id`, `oic_code`, `intitule`, `rang`, `oic_level`), `course` (objet avec `.title`, `.college: list[str]`, `.display_item_number`)
- Produces: `open_oic_eval_dialog(oic, course, refresh_fn=None) -> None`

Pas de test automatisé — aucun composant dialog NiceGUI n'a de test dans ce projet (vérification manuelle en Task 11).

- [ ] **Step 1: Créer le fichier**

Créer `frontend/components/oic_eval_dialog.py` :

```python
"""
oic_eval_dialog.py — Synapse
------------------------------
Dialog de validation active d'un OIC via AnythingLLM : génère 3-5 questions
(QCM + ouvertes) grounded RAG sur le workspace du collège, quiz une question
à la fois avec feedback immédiat, puis récapitulatif et progression de niveau.
"""
from __future__ import annotations

import asyncio
import json

from nicegui import ui

from backend.core.reviews import local_store as ls
from backend.core.lisa import evaluator
from backend.core.lisa.anythingllm_client import (
    resolve_workspace_slug,
    AnythingLLMUnavailableError,
    WorkspaceNotFoundError,
)

_VERDICT_COLORS = {"correct": "green-600", "partial": "orange-500", "incorrect": "red-600"}
_VERDICT_LABELS = {"correct": "ACQUIS", "partial": "PARTIEL", "incorrect": "ÉCHEC"}


def open_oic_eval_dialog(oic, course, refresh_fn=None) -> None:
    """Ouvre la dialog de quiz IA pour valider un OIC via AnythingLLM."""
    item_number = str(getattr(course, "display_item_number", "") or "")
    course_title = f"ITEM {item_number} - {course.title}" if item_number else (course.title or "")
    college_name = course.college[0] if getattr(course, "college", None) else ""

    state: dict = {
        "questions": [],
        "index": 0,
        "results": [],
        "records": [],
        "workspace_slug": None,
    }

    with ui.dialog() as dialog, ui.card().classes("w-[600px] max-w-[95vw] p-4 rounded-2xl"):
        with ui.row().classes("w-full items-center justify-between mb-2"):
            ui.label(f"{oic['oic_code'] or ''} · Rang {oic['rang']}").classes("font-semibold text-sm")
            ui.button(icon="close", on_click=dialog.close).props("flat dense round size=sm")

        content_area = ui.column().classes("w-full gap-3")

    def _render_error(message: str) -> None:
        content_area.clear()
        with content_area:
            ui.icon("wifi_off", color="red").classes("text-3xl self-center")
            ui.label(message).classes("text-sm text-red-500 text-center")

    def _render_loading(message: str) -> None:
        content_area.clear()
        with content_area:
            ui.spinner(size="lg").classes("self-center")
            ui.label(message).classes("text-sm text-slate-400 text-center")

    def _render_feedback(result) -> None:
        content_area.clear()
        with content_area:
            ui.label(f"{_VERDICT_LABELS[result.verdict]} · {result.score}%").classes(
                f"font-bold text-{_VERDICT_COLORS[result.verdict]}"
            )
            if result.explication:
                ui.label(result.explication).classes("text-sm")
            if result.rappel_cours:
                ui.label(result.rappel_cours).classes("text-xs text-slate-400 italic")
            is_last = state["index"] + 1 >= len(state["questions"])
            ui.button(
                "Voir le résultat" if is_last else "Question suivante →",
                on_click=_next_question,
            ).props("unelevated color=teal")

    def _next_question() -> None:
        state["index"] += 1
        if state["index"] >= len(state["questions"]):
            _render_recap()
        else:
            _render_question()

    def _render_question() -> None:
        content_area.clear()
        q = state["questions"][state["index"]]
        with content_area:
            ui.label(f"Question {state['index'] + 1}/{len(state['questions'])}").classes(
                "text-xs text-slate-400"
            )
            ui.label(q.enonce).classes("text-base font-medium")

            if q.type == "qcm":
                radio = ui.radio({i: opt for i, opt in enumerate(q.options or [])}).classes("w-full")

                def _submit_qcm(r=radio, question=q) -> None:
                    if r.value is None:
                        ui.notify("Choisissez une réponse", type="warning")
                        return
                    result = evaluator.grade_qcm(question, r.value)
                    state["results"].append(result)
                    state["records"].append({
                        "enonce": question.enonce, "type": "qcm",
                        "reponse": question.options[r.value] if question.options else "",
                        "verdict": result.verdict, "score": result.score,
                    })
                    _render_feedback(result)

                ui.button("Valider", on_click=_submit_qcm).props("unelevated color=teal")
            else:
                textarea = ui.textarea(label="Votre réponse").props("outlined").classes("w-full")

                async def _submit_open(t=textarea, question=q) -> None:
                    response = (t.value or "").strip()
                    if not response:
                        ui.notify("Répondez avant de valider", type="warning")
                        return
                    _render_loading("Correction en cours…")
                    try:
                        result = await asyncio.to_thread(
                            evaluator.evaluate_open_answer, question, response, state["workspace_slug"]
                        )
                    except AnythingLLMUnavailableError as exc:
                        _render_error(f"AnythingLLM inaccessible : {exc}")
                        return
                    state["results"].append(result)
                    state["records"].append({
                        "enonce": question.enonce, "type": "ouverte", "reponse": response,
                        "verdict": result.verdict, "score": result.score,
                    })
                    _render_feedback(result)

                ui.button("Valider", on_click=_submit_open).props("unelevated color=teal")

    def _render_recap() -> None:
        content_area.clear()
        session_score = evaluator.aggregate_session_score(state["results"])
        previous = [row["session_score"] for row in ls.get_oic_attempts(oic["id"], limit=2)]
        old_level = oic["oic_level"] or 0
        new_level = evaluator.next_oic_level(old_level, session_score, previous)
        ls.save_oic_attempt(oic["id"], session_score, json.dumps(state["records"], ensure_ascii=False))
        ls.update_oic_level(oic["id"], new_level)

        with content_area:
            ui.label(f"Score global : {session_score}%").classes("text-lg font-bold")
            ui.label(f"Niveau {old_level} → {new_level}").classes("text-sm text-slate-400")
            with ui.row().classes("gap-2 mt-2"):
                ui.button("Recommencer", on_click=lambda: asyncio.ensure_future(_start())).props(
                    "outline color=teal"
                )
                ui.button("Fermer", on_click=dialog.close).props("unelevated color=teal")

    async def _start() -> None:
        state["index"] = 0
        state["results"] = []
        state["records"] = []
        _render_loading("Résolution du workspace…")
        try:
            if state["workspace_slug"] is None:
                state["workspace_slug"] = await asyncio.to_thread(resolve_workspace_slug, college_name)
        except (WorkspaceNotFoundError, AnythingLLMUnavailableError) as exc:
            _render_error(str(exc))
            return

        _render_loading("Génération des questions…")
        try:
            state["questions"] = await asyncio.to_thread(
                evaluator.generate_questions, course_title, oic["intitule"], oic["rang"], state["workspace_slug"]
            )
        except AnythingLLMUnavailableError as exc:
            _render_error(str(exc))
            return
        _render_question()

    if refresh_fn:
        dialog.on("hide", lambda: refresh_fn())

    ui.timer(0.05, lambda: asyncio.ensure_future(_start()), once=True)
    dialog.open()
```

- [ ] **Step 2: Vérifier la syntaxe**

Run: `python -c "import ast; ast.parse(open('frontend/components/oic_eval_dialog.py', encoding='utf-8').read())"`
Expected: pas d'exception (syntaxe valide)

- [ ] **Step 3: Commit**

```bash
git add frontend/components/oic_eval_dialog.py
git commit -m "feat: add OIC quiz evaluation dialog"
```

---

### Task 10: Branchement dans `lisa_dialog.py` — bouton "Évaluer" + badge de niveau

**Files:**
- Modify: `frontend/components/lisa_dialog.py`

**Interfaces:**
- Consumes: `open_oic_eval_dialog(oic, course, refresh_fn=None)` (Task 9)

Pas de test automatisé (voir Task 9). Vérification manuelle en Task 11.

- [ ] **Step 1: Importer `open_oic_eval_dialog`**

Dans `frontend/components/lisa_dialog.py`, modifier l'import en ligne 13 :

```python
from backend.core.lisa.scraper import scrape_oic, LisaFetchError
from frontend.components.oic_eval_dialog import open_oic_eval_dialog
```

- [ ] **Step 2: Ajouter le helper de badge de niveau**

Insérer juste avant `def _render_oics(oics: list) -> None:` (ligne 111) :

```python
    def _level_badge(level: int) -> tuple[str, str]:
        if level >= 5:
            return (
                "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
                "★ Maîtrisé",
            )
        if level >= 3:
            return "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300", f"Lvl {level}"
        return "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300", f"Lvl {level}"

```

- [ ] **Step 3: Ajouter le bouton "Évaluer" et le badge dans la ligne OIC**

Remplacer (lignes 204-206) :

```python
                                    ui.icon(icon_name).classes(
                                        f"text-[20px] shrink-0 mt-0.5 {icon_cls}"
                                    )
```

par :

```python
                                    with ui.column().classes("items-end gap-1 shrink-0"):
                                        ui.icon(icon_name).classes(f"text-[20px] mt-0.5 {icon_cls}")
                                        level = oic["oic_level"] or 0
                                        if level > 0:
                                            level_cls, level_text = _level_badge(level)
                                            ui.label(level_text).classes(
                                                f"text-[8px] font-bold px-1.5 py-0.5 rounded {level_cls}"
                                            )
                                        ui.button(icon="school").props(
                                            "flat dense round size=xs"
                                        ).classes(
                                            "text-violet-400 hover:text-violet-600"
                                        ).on(
                                            "click.stop",
                                            lambda o=oic: open_oic_eval_dialog(
                                                o, course,
                                                refresh_fn=lambda: asyncio.ensure_future(_load(force=True)),
                                            ),
                                        ).tooltip("Évaluer cet OIC")
```

**Note de vérification manuelle (Task 11) :** le modificateur `.on("click.stop", ...)` doit empêcher le clic sur le bouton de déclencher aussi le toggle `mastered` du `div` parent (ligne 186, `.on("click", ...)`). Si le clic sur "Évaluer" bascule quand même la case à cocher, remplacer `"click.stop"` par un événement personnalisé ou déplacer le bouton hors du `div` cliquable parent.

- [ ] **Step 4: Vérifier la syntaxe**

Run: `python -c "import ast; ast.parse(open('frontend/components/lisa_dialog.py', encoding='utf-8').read())"`
Expected: pas d'exception (syntaxe valide)

- [ ] **Step 5: Commit**

```bash
git add frontend/components/lisa_dialog.py
git commit -m "feat: wire OIC evaluation button and level badge into lisa_dialog"
```

---

### Task 11: Vérification manuelle end-to-end

**Files:** aucun (vérification uniquement)

- [ ] **Step 1: Lancer la suite de tests complète**

Run: `pytest tests/ -v`
Expected: tous les tests passent (hors échecs préexistants déjà connus dans `test_lisa_scraper.py`, sans lien avec ce plan)

- [ ] **Step 2: Lancer l'application**

Run: `python main.py` (ou la commande habituelle de lancement de Synapse)

- [ ] **Step 3: Configurer AnythingLLM dans Settings**

Ouvrir `/settings` → section "AnythingLLM" → renseigner l'URL (`http://localhost:3001`) et la clé API → cliquer "Tester la connexion" → vérifier le message "Connecté ✓ — N workspace(s) trouvé(s)" (AnythingLLM doit tourner en local avec au moins un workspace importé).

- [ ] **Step 4: Ouvrir un cours et déclencher l'évaluation d'un OIC**

Ouvrir un cours ayant des OIC LiSA en cache → ouvrir la dialog LiSA → cliquer le bouton "Évaluer" (icône `school`) sur un OIC → vérifier :
- le clic n'a pas basculé la case `mastered` du même coup (voir note Task 10)
- la génération affiche un spinner puis une première question
- répondre à une question QCM affiche un feedback immédiat coloré
- répondre à une question ouverte déclenche un appel IA (spinner "Correction en cours…") puis un feedback
- après la dernière question, le récapitulatif affiche le score global et l'évolution de niveau
- fermer la dialog puis rouvrir la dialog LiSA : le badge de niveau à côté de l'OIC reflète le nouveau niveau

- [ ] **Step 5: Tester les cas d'erreur**

Arrêter AnythingLLM → recliquer "Évaluer" sur un OIC → vérifier que le message d'erreur "AnythingLLM inaccessible sur ..." s'affiche proprement dans la dialog (pas de crash, pas de dialog vide).

- [ ] **Step 6: Commit final (si des ajustements manuels ont été faits)**

```bash
git add -A
git commit -m "fix: manual verification adjustments for OIC AnythingLLM evaluation"
```

(Ne committer que si des changements ont réellement été nécessaires à cette étape.)
