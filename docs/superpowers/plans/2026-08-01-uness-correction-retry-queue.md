# File d'attente persistante des corrections UNESS en échec — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Détecter les corrections Gemini en échec (total ou partiel — moins de questions que le HTML source), les stocker de façon persistante, les retenter automatiquement (3 tentatives, délai croissant, via la boucle de fond existante) et les rendre visibles/relançables manuellement depuis la page Annales.

**Architecture:** Nouvelle table SQLite `uness_correction_failures` (via `local_store`, même pattern que `uness_annales`). `gemini_autocorrect.correct_directory` est refactoré pour extraire la correction d'un seul quiz dans `_correct_one_quiz`, réutilisée par un nouveau `retry_failed_quiz(failure_id)`. La boucle de fond existante (`backend/core/background.py: run_background_tasks`, cycle 5 min) gagne une étape de retry. La page `/annales` affiche un bandeau + la sidebar un badge de compteur.

**Tech Stack:** Python 3.11, SQLite (`local_store`), NiceGUI (frontend), pytest + `unittest.mock`.

## Global Constraints

- Design de référence : `docs/superpowers/specs/2026-08-01-uness-correction-retry-queue-design.md` — toute divergence avec ce plan doit être résolue en faveur du spec.
- Retry automatique **borné à 3 tentatives**, délais 30 s / 2 min / 10 min (arrondis à la granularité du cycle de fond de 5 min).
- Un quiz incomplet (moins de questions que le HTML source) n'est **jamais importé partiellement** — rien n'est écrit tant que le compte ne correspond pas.
- Aucune nouvelle dépendance, aucun nouveau scheduler — tout passe par `local_store` (SQLite déjà en place) et `run_background_tasks` (boucle déjà en place).
- Suivre le style existant du fichier modifié à chaque fois (imports locaux vs top-level, docstrings, nommage) plutôt qu'imposer un style uniforme nouveau.

---

### Task 1: Table et CRUD `uness_correction_failures` dans `local_store.py`

**Files:**
- Modify: `backend/core/reviews/local_store.py` (ajouter la migration après `_migrate_uness_annales()` ligne 426, et les fonctions CRUD après `set_session_annale_id` ligne ~1500)
- Test: `tests/test_uness_correction_failures.py` (nouveau)

**Interfaces:**
- Produces:
  - `record_uness_correction_failure(*, bridge_folder: str, quiz_title: str, collected_at: str, error_message: str) -> int`
  - `resolve_uness_correction_failure(quiz_title: str, collected_at: str) -> None`
  - `get_uness_correction_failure(failure_id: int) -> dict | None`
  - `list_pending_uness_correction_failures(*, due_only: bool = False) -> list[dict]`
  - `count_pending_uness_correction_failures() -> int`
  - `reset_uness_correction_failure_attempts(failure_id: int) -> None`

- [ ] **Step 1: Écrire le test de la migration + CRUD de base**

```python
"""Tests for the uness_correction_failures retry-queue table and its local_store CRUD."""

from __future__ import annotations

import pytest

from backend.core.reviews import local_store


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def test_record_creates_a_pending_entry_with_attempt_1_and_a_near_future_retry() -> None:
    failure_id = local_store.record_uness_correction_failure(
        bridge_folder="UNESS/à_vérifier/session-1",
        quiz_title="SQI1",
        collected_at="2026-08-01T09:00:00+04:00",
        error_message="Extra data: line 42 column 3 (char 900)",
    )

    failure = local_store.get_uness_correction_failure(failure_id)
    assert failure is not None
    assert failure["quiz_title"] == "SQI1"
    assert failure["attempts"] == 1
    assert failure["status"] == "pending"
    assert failure["error_message"] == "Extra data: line 42 column 3 (char 900)"


def test_recording_the_same_quiz_twice_upserts_instead_of_duplicating() -> None:
    """Two failures for the same (quiz_title, collected_at) must stay one row —
    otherwise the banner grows forever for a quiz that keeps failing every cycle."""
    local_store.record_uness_correction_failure(
        bridge_folder="UNESS/à_vérifier/session-1",
        quiz_title="SQI1",
        collected_at="2026-08-01T09:00:00+04:00",
        error_message="première erreur",
    )

    second_id = local_store.record_uness_correction_failure(
        bridge_folder="UNESS/archives/pneumologie",
        quiz_title="SQI1",
        collected_at="2026-08-01T09:00:00+04:00",
        error_message="deuxième erreur",
    )

    failures = local_store.list_pending_uness_correction_failures()
    assert len(failures) == 1
    assert failures[0]["id"] == second_id
    assert failures[0]["attempts"] == 2
    assert failures[0]["error_message"] == "deuxième erreur"
    assert failures[0]["bridge_folder"] == "UNESS/archives/pneumologie"


def test_resolve_marks_matching_pending_entry_as_resolved() -> None:
    local_store.record_uness_correction_failure(
        bridge_folder="UNESS/à_vérifier/session-1",
        quiz_title="SQI1",
        collected_at="2026-08-01T09:00:00+04:00",
        error_message="erreur",
    )

    local_store.resolve_uness_correction_failure("SQI1", "2026-08-01T09:00:00+04:00")

    assert local_store.list_pending_uness_correction_failures() == []


def test_count_pending_reflects_only_unresolved_entries() -> None:
    local_store.record_uness_correction_failure(
        bridge_folder="f", quiz_title="SQI1", collected_at="2026-08-01T09:00:00+04:00", error_message="e",
    )
    local_store.record_uness_correction_failure(
        bridge_folder="f", quiz_title="DP1", collected_at="2026-08-01T09:00:00+04:00", error_message="e",
    )
    assert local_store.count_pending_uness_correction_failures() == 2

    local_store.resolve_uness_correction_failure("DP1", "2026-08-01T09:00:00+04:00")
    assert local_store.count_pending_uness_correction_failures() == 1


def test_reset_attempts_clears_the_counter_and_pulls_next_retry_to_now() -> None:
    failure_id = local_store.record_uness_correction_failure(
        bridge_folder="f", quiz_title="SQI1", collected_at="2026-08-01T09:00:00+04:00", error_message="e",
    )
    local_store.record_uness_correction_failure(
        bridge_folder="f", quiz_title="SQI1", collected_at="2026-08-01T09:00:00+04:00", error_message="e",
    )
    local_store.record_uness_correction_failure(
        bridge_folder="f", quiz_title="SQI1", collected_at="2026-08-01T09:00:00+04:00", error_message="e",
    )
    assert local_store.list_pending_uness_correction_failures(due_only=True) == []  # 3 tentatives épuisées

    local_store.reset_uness_correction_failure_attempts(failure_id)

    due = local_store.list_pending_uness_correction_failures(due_only=True)
    assert len(due) == 1
    assert due[0]["attempts"] == 0


def test_due_only_excludes_entries_whose_next_retry_is_in_the_future() -> None:
    from datetime import timedelta

    failure_id = local_store.record_uness_correction_failure(
        bridge_folder="f", quiz_title="SQI1", collected_at="2026-08-01T09:00:00+04:00", error_message="e",
    )
    failure = local_store.get_uness_correction_failure(failure_id)
    assert failure is not None
    # 1ère tentative : délai de 30s, donc pas encore "due" juste après l'appel.
    assert local_store.list_pending_uness_correction_failures(due_only=True) == []
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_uness_correction_failures.py -v`
Expected: FAIL avec `AttributeError: module 'backend.core.reviews.local_store' has no attribute 'record_uness_correction_failure'`

- [ ] **Step 3: Ajouter la migration**

Dans `backend/core/reviews/local_store.py`, juste après la fonction `_migrate_uness_annales` (qui se termine ligne 490), ajouter :

```python
_UNESS_RETRY_DELAYS_SECONDS = [30, 120, 600]  # après la 1ère, 2e, 3e tentative


def _migrate_uness_correction_failures() -> None:
    """File d'attente persistante des corrections Gemini en échec (échec total
    ou question manquante) — retry automatique borné + bandeau/badge UI."""
    with _conn() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS uness_correction_failures (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                bridge_folder   TEXT NOT NULL,
                quiz_title      TEXT NOT NULL,
                collected_at    TEXT NOT NULL,
                error_message   TEXT NOT NULL,
                attempts        INTEGER NOT NULL DEFAULT 0,
                next_retry_at   TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'pending',
                created_at      TEXT NOT NULL,
                last_attempt_at TEXT
            )"""
        )
```

Puis, dans `init_db()`, juste après la ligne `_migrate_uness_annales()` (ligne 426), ajouter l'appel :

```python
    _migrate_uness_correction_failures()
```

- [ ] **Step 4: Ajouter les fonctions CRUD**

Toujours dans `backend/core/reviews/local_store.py`, après `set_session_annale_id` (qui se termine vers la ligne 1496), ajouter :

```python
def record_uness_correction_failure(
    *, bridge_folder: str, quiz_title: str, collected_at: str, error_message: str
) -> int:
    """Upsert par (quiz_title, collected_at) : incrémente attempts et repousse
    next_retry_at au lieu de créer une deuxième ligne pour le même quiz qui
    échoue à répétition."""
    from datetime import timedelta

    now = _now()
    with _conn() as con:
        row = con.execute(
            "SELECT id, attempts FROM uness_correction_failures "
            "WHERE quiz_title = ? AND collected_at = ? AND status = 'pending'",
            (quiz_title, collected_at),
        ).fetchone()
        if row is not None:
            attempts = int(row["attempts"]) + 1
            delay = _UNESS_RETRY_DELAYS_SECONDS[min(attempts - 1, len(_UNESS_RETRY_DELAYS_SECONDS) - 1)]
            next_retry_at = (datetime.datetime.fromisoformat(now) + timedelta(seconds=delay)).isoformat()
            con.execute(
                "UPDATE uness_correction_failures SET attempts = ?, next_retry_at = ?, "
                "error_message = ?, bridge_folder = ?, last_attempt_at = ? WHERE id = ?",
                (attempts, next_retry_at, error_message, bridge_folder, now, row["id"]),
            )
            return int(row["id"])
        delay = _UNESS_RETRY_DELAYS_SECONDS[0]
        next_retry_at = (datetime.datetime.fromisoformat(now) + timedelta(seconds=delay)).isoformat()
        cur = con.execute(
            "INSERT INTO uness_correction_failures "
            "(bridge_folder, quiz_title, collected_at, error_message, attempts, "
            "next_retry_at, status, created_at, last_attempt_at) "
            "VALUES (?,?,?,?,1,?,'pending',?,?)",
            (bridge_folder, quiz_title, collected_at, error_message, next_retry_at, now, now),
        )
        return int(cur.lastrowid)


def resolve_uness_correction_failure(quiz_title: str, collected_at: str) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE uness_correction_failures SET status = 'resolved' "
            "WHERE quiz_title = ? AND collected_at = ? AND status = 'pending'",
            (quiz_title, collected_at),
        )


def get_uness_correction_failure(failure_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM uness_correction_failures WHERE id = ?", (failure_id,)
        ).fetchone()
    return dict(row) if row else None


def list_pending_uness_correction_failures(*, due_only: bool = False) -> list[dict]:
    with _conn() as con:
        if due_only:
            rows = con.execute(
                "SELECT * FROM uness_correction_failures "
                "WHERE status = 'pending' AND attempts < 3 AND next_retry_at <= ? "
                "ORDER BY next_retry_at",
                (_now(),),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM uness_correction_failures WHERE status = 'pending' "
                "ORDER BY created_at DESC"
            ).fetchall()
    return [dict(row) for row in rows]


def count_pending_uness_correction_failures() -> int:
    with _conn() as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM uness_correction_failures WHERE status = 'pending'"
        ).fetchone()
    return int(row["n"]) if row else 0


def reset_uness_correction_failure_attempts(failure_id: int) -> None:
    """Utilisé par le bouton "Relancer" manuel : redonne 3 tentatives auto
    fraîches plutôt que de laisser l'entrée bloquée si le clic échoue encore."""
    with _conn() as con:
        con.execute(
            "UPDATE uness_correction_failures SET attempts = 0, next_retry_at = ? WHERE id = ?",
            (_now(), failure_id),
        )
```

- [ ] **Step 5: Lancer les tests, vérifier qu'ils passent**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_uness_correction_failures.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/core/reviews/local_store.py tests/test_uness_correction_failures.py
git commit -m "feat(uness): table et CRUD de la file d'attente des corrections en échec"
```

---

### Task 2: Extraire `_correct_one_quiz` de `correct_directory` (refactor pur, sans changement de comportement)

**Files:**
- Modify: `backend/core/uness/gemini_autocorrect.py:156-244` (fonction `correct_directory`)
- Test: `tests/test_gemini_autocorrect.py` (existant — ne doit nécessiter AUCUNE modification, sert de filet de sécurité pour ce refactor)

**Interfaces:**
- Consumes: rien de nouveau — réutilise `_quiz_images`, `_clean_moodle_html`, `_parsed_response`, `gemini_conversion.convert_with_bridge`, `generate_uness_correction` déjà présents dans ce fichier.
- Produces: `_correct_one_quiz(bridge_path: Path, bridge: dict, quiz: dict, prompt: str, folder: Path, service: AIService | None) -> tuple[str | None, str | None, int, int]` — retourne `(written_filename, message, input_tokens, output_tokens)`. `written_filename` est non-`None` en cas de succès (le fichier canonique a été écrit dans `import_service.VERIFIED_DIR`) ; `message` est non-`None` soit comme avertissement non bloquant sur un succès (images manquantes), soit comme raison d'échec quand `written_filename is None`.

- [ ] **Step 1: Lancer la suite existante pour capturer l'état de référence avant refactor**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_gemini_autocorrect.py -v`
Expected: PASS (11 tests) — c'est l'état qu'on doit préserver à l'identique après le refactor.

- [ ] **Step 2: Extraire la fonction**

Remplacer entièrement la fonction `correct_directory` (lignes 156-244 de `backend/core/uness/gemini_autocorrect.py`) par :

```python
def _correct_one_quiz(
    bridge_path: Path,
    bridge: dict,
    quiz: dict,
    prompt: str,
    folder: Path,
    service: AIService | None,
) -> tuple[str | None, str | None, int, int]:
    """Corrige un seul quiz avec Gemini et écrit sa sortie canonique dans
    import_service.VERIFIED_DIR.

    Retourne (written_filename, message, input_tokens, output_tokens) :
      - written_filename n'est pas None en cas de succès (message peut quand
        même porter un avertissement non bloquant, ex. images manquantes).
      - written_filename est None en cas d'échec (message est alors toujours
        renseigné : erreur API, JSON invalide, ou question(s) manquante(s))."""
    title = str(quiz.get("title", bridge_path.stem))
    try:
        images, missing = _quiz_images(quiz, folder)
        raw_html = quiz.get("html", "")
        cleaned_content = _clean_moodle_html(raw_html) if raw_html else ""

        message = (
            f"{prompt}\n\n"
            f"{json.dumps({'title': quiz.get('title'), 'content': cleaned_content}, ensure_ascii=False)}"
        )

        max_retries = 5
        response = None
        for attempt in range(max_retries):
            try:
                response = generate_uness_correction(
                    message,
                    images=images,
                    context=title,
                    service=service,
                )
                break
            except AIServiceError as err:
                if ("429" in str(err) or "Too Many Requests" in str(err)) and attempt < max_retries - 1:
                    import time
                    time.sleep(10 * (attempt + 1))
                    continue
                raise err

        if response is None:
            raise AIServiceError("Aucune réponse obtenue du service IA.")

        payload = _parsed_response(response.text)
        quiz_objects = payload if isinstance(payload, list) else [payload]
        exams = gemini_conversion.convert_with_bridge(quiz_objects, bridge)

        written = None
        for index, exam in enumerate(exams):
            suffix = f"-{index}" if len(exams) > 1 else ""
            out_path = import_service.VERIFIED_DIR / f"{_slug(title)}-{bridge_path.stem}{suffix}.json"
            out_path.write_text(
                json.dumps(exam.to_dict(), ensure_ascii=False) + "\n", encoding="utf-8"
            )
            written = out_path.name

        warning = f"Images manquantes (ignorées) : {', '.join(missing)}" if missing else None
        return written, warning, response.input_tokens or 0, response.output_tokens or 0
    except (AIServiceError, ValueError, KeyError, json.JSONDecodeError, OSError) as exc:
        return None, str(exc), 0, 0


def correct_directory(folder: Path, *, service: AIService | None = None) -> dict:
    """Call Gemini once per quiz for every bridge JSON directly in `folder`,
    converting each response with its own bridge on the spot and writing the
    already-canonical exam into UNESS/vérifiés/."""
    folder = Path(folder)
    corrected: list[str] = []
    errors: list[dict[str, str]] = []
    input_tokens = 0
    output_tokens = 0

    if not folder.is_dir():
        errors.append({"file": str(folder), "error": "Dossier introuvable"})
        return {
            "corrected": corrected,
            "errors": errors,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

    import_service.VERIFIED_DIR.mkdir(parents=True, exist_ok=True)
    for bridge_path in _find_bridge_files(folder):
        bridge = json.loads(bridge_path.read_text(encoding="utf-8"))
        prompt = _prompt_text(bridge)
        for quiz in bridge.get("contents", []):
            written, message, in_tok, out_tok = _correct_one_quiz(
                bridge_path, bridge, quiz, prompt, folder, service
            )
            input_tokens += in_tok
            output_tokens += out_tok
            if written:
                corrected.append(written)
            if message:
                errors.append({"file": bridge_path.name, "error": message})

    return {
        "corrected": corrected,
        "errors": errors,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
```

- [ ] **Step 3: Lancer la suite existante, vérifier qu'elle passe toujours à l'identique**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_gemini_autocorrect.py -v`
Expected: PASS (11 tests, aucune régression — ce refactor ne change aucun comportement observable)

- [ ] **Step 4: Commit**

```bash
git add backend/core/uness/gemini_autocorrect.py
git commit -m "refactor(uness): extraire _correct_one_quiz de correct_directory"
```

---

### Task 3: Détection d'un quiz incomplet (question manquante)

**Files:**
- Modify: `backend/core/uness/gemini_autocorrect.py` (fonction `_correct_one_quiz`)
- Test: `tests/test_gemini_autocorrect.py`

**Interfaces:**
- Produces: `_expected_question_count(html: str) -> int`

- [ ] **Step 1: Écrire le test du cas incomplet**

Ajouter à la fin de `tests/test_gemini_autocorrect.py` :

```python
def test_correct_directory_rejects_a_quiz_with_fewer_questions_than_the_source_html(
    tmp_path, _isolated_verified_dir
):
    """Le cas exact constaté en prod : DP1 a 6 questions sur UNESS (6 div.que
    dans le HTML du bridge), Gemini n'en renvoie que 5 dans un JSON par
    ailleurs valide — ça doit être traité comme un échec, rien n'est écrit."""
    html = "".join(f'<div class="que"><div class="qtext">Q{i}</div></div>' for i in range(1, 7))
    _bridge_file(tmp_path, name="dp1-20260730T090000Z.json")
    bridge_path = tmp_path / "dp1-20260730T090000Z.json"
    payload = json.loads(bridge_path.read_text(encoding="utf-8"))
    payload["contents"][0]["html"] = html
    bridge_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    service = Mock()
    five_questions = {
        "quiz_title": "DP1\nTest",
        "questions": [
            {"id": f"q{i}", "type_question": "QRM", "enonce": f"Q{i}", "propositions": []}
            for i in range(1, 6)
        ],
    }
    service.generate.return_value = AIResponse(
        text=json.dumps(five_questions), model=AIModel.FLASH, input_tokens=100, output_tokens=20
    )

    result = gemini_autocorrect.correct_directory(tmp_path, service=service)

    assert result["corrected"] == []
    assert len(result["errors"]) == 1
    assert "5/6" in result["errors"][0]["error"] or "incomplète" in result["errors"][0]["error"].lower()
    assert list(_isolated_verified_dir.glob("*.json")) == []


def test_correct_directory_accepts_a_quiz_whose_question_count_matches_the_source_html(
    tmp_path, _isolated_verified_dir
):
    """Contrôle négatif : un compte qui correspond ne doit jamais être bloqué —
    couvre aussi le cas des fixtures existantes dont le HTML factice
    ("<div>question html</div>") ne contient aucun div.que (0 attendu, 0 reçu)."""
    html = "".join(f'<div class="que"><div class="qtext">Q{i}</div></div>' for i in range(1, 4))
    _bridge_file(tmp_path, name="dp1-20260730T090000Z.json")
    bridge_path = tmp_path / "dp1-20260730T090000Z.json"
    payload = json.loads(bridge_path.read_text(encoding="utf-8"))
    payload["contents"][0]["html"] = html
    bridge_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    service = Mock()
    three_questions = {
        "quiz_title": "DP1\nTest",
        "questions": [
            {"id": f"q{i}", "type_question": "QRM", "enonce": f"Q{i}", "propositions": []}
            for i in range(1, 4)
        ],
    }
    service.generate.return_value = AIResponse(
        text=json.dumps(three_questions), model=AIModel.FLASH, input_tokens=100, output_tokens=20
    )

    result = gemini_autocorrect.correct_directory(tmp_path, service=service)

    assert len(result["corrected"]) == 1
    assert result["errors"] == []
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec du premier (le deuxième doit déjà passer)**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_gemini_autocorrect.py -k "question_count_or_source_html or fewer_questions" -v`
Expected: `test_correct_directory_rejects_a_quiz_with_fewer_questions_than_the_source_html` FAIL (rien n'empêche encore l'écriture) ; `test_correct_directory_accepts_a_quiz_whose_question_count_matches_the_source_html` PASS déjà (comportement inchangé).

- [ ] **Step 3: Ajouter `_expected_question_count` et l'appeler dans `_correct_one_quiz`**

Dans `backend/core/uness/gemini_autocorrect.py`, ajouter juste avant `_correct_one_quiz` :

```python
def _expected_question_count(html: str) -> int:
    """Compte les blocs de question réels du HTML Moodle du bridge — même
    convention de sélection que _clean_moodle_html : les div.que qui ne sont
    pas le bloc de description partagé (vignette clinique, pas une question)."""
    soup = BeautifulSoup(html, "html.parser")
    count = 0
    for q_div in soup.select("div.que, div[id^='question-']"):
        if "description" in q_div.get("class", []):
            continue
        count += 1
    return count
```

Puis, dans `_correct_one_quiz`, juste après la ligne `raw_html = quiz.get("html", "")` ajouter :

```python
        expected_questions = _expected_question_count(raw_html) if raw_html else 0
```

Et juste après la ligne `exams = gemini_conversion.convert_with_bridge(quiz_objects, bridge)`, ajouter la vérification avant la boucle d'écriture :

```python
        got_questions = sum(len(exam.questions) for exam in exams)
        if expected_questions and got_questions < expected_questions:
            return (
                None,
                f"Réponse incomplète : {got_questions}/{expected_questions} questions",
                response.input_tokens or 0,
                response.output_tokens or 0,
            )
```

- [ ] **Step 4: Lancer toute la suite, vérifier qu'elle passe**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_gemini_autocorrect.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/core/uness/gemini_autocorrect.py tests/test_gemini_autocorrect.py
git commit -m "feat(uness): détecter un quiz dont Gemini a tronqué des questions"
```

---

### Task 4: Enregistrer/résoudre les échecs dans la file d'attente

**Files:**
- Modify: `backend/core/uness/gemini_autocorrect.py` (fonction `correct_directory`)
- Modify: `tests/test_gemini_autocorrect.py` (ajouter la fixture d'isolation DB, autouse)

**Interfaces:**
- Consumes: `local_store.record_uness_correction_failure`, `local_store.resolve_uness_correction_failure` (Task 1)

- [ ] **Step 1: Isoler la DB dans les tests existants (préalable nécessaire)**

`correct_directory` va appeler `local_store` à partir de ce commit — sans isolation, les tests écriraient dans la vraie base `data/synapse_local.db` de l'utilisateur. Ajouter en haut de `tests/test_gemini_autocorrect.py`, juste après les imports existants :

```python
from backend.core.reviews import local_store


@pytest.fixture(autouse=True)
def _isolated_local_store_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "local-store-test.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)
```

- [ ] **Step 2: Lancer la suite existante, vérifier qu'elle passe toujours (pure isolation, pas encore de nouveau comportement)**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_gemini_autocorrect.py -v`
Expected: PASS (13 tests)

- [ ] **Step 3: Écrire les tests du nouveau comportement**

Ajouter à la fin de `tests/test_gemini_autocorrect.py` :

```python
def test_correct_directory_records_a_pending_failure_on_invalid_json(tmp_path, _isolated_verified_dir):
    _bridge_file(tmp_path, title="DP1\nTest")
    service = Mock()
    service.generate.return_value = AIResponse(
        text="not valid json", model=AIModel.FLASH, input_tokens=10, output_tokens=1
    )

    gemini_autocorrect.correct_directory(tmp_path, service=service)

    failures = local_store.list_pending_uness_correction_failures()
    assert len(failures) == 1
    assert failures[0]["quiz_title"] == "DP1\nTest"
    assert failures[0]["collected_at"] == "2026-07-30T09:00:00+00:00"


def test_correct_directory_resolves_a_previously_recorded_failure_on_success(tmp_path, _isolated_verified_dir):
    local_store.record_uness_correction_failure(
        bridge_folder=str(tmp_path),
        quiz_title="DP1\nTest",
        collected_at="2026-07-30T09:00:00+00:00",
        error_message="ancien échec",
    )
    _bridge_file(tmp_path, title="DP1\nTest")
    service = Mock()
    service.generate.return_value = _quiz_response("DP1\nTest")

    gemini_autocorrect.correct_directory(tmp_path, service=service)

    assert local_store.list_pending_uness_correction_failures() == []


def test_correct_directory_does_not_record_a_failure_when_correction_succeeds(tmp_path, _isolated_verified_dir):
    _bridge_file(tmp_path, title="DP1\nTest")
    service = Mock()
    service.generate.return_value = _quiz_response("DP1\nTest")

    gemini_autocorrect.correct_directory(tmp_path, service=service)

    assert local_store.list_pending_uness_correction_failures() == []
```

- [ ] **Step 4: Lancer les tests, vérifier l'échec des deux premiers**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_gemini_autocorrect.py -k "records_a_pending or resolves_a_previously" -v`
Expected: FAIL — rien n'enregistre encore d'échec.

- [ ] **Step 5: Wirer `local_store` dans `correct_directory`**

Ajouter en haut de `backend/core/uness/gemini_autocorrect.py`, dans le bloc d'imports :

```python
from backend.core.reviews import local_store
```

Puis, dans `correct_directory`, remplacer la boucle interne :

```python
        for quiz in bridge.get("contents", []):
            written, message, in_tok, out_tok = _correct_one_quiz(
                bridge_path, bridge, quiz, prompt, folder, service
            )
            input_tokens += in_tok
            output_tokens += out_tok
            if written:
                corrected.append(written)
            if message:
                errors.append({"file": bridge_path.name, "error": message})
```

par :

```python
        collected_at = str(bridge.get("source", {}).get("collected_at", ""))
        for quiz in bridge.get("contents", []):
            title = str(quiz.get("title", bridge_path.stem))
            written, message, in_tok, out_tok = _correct_one_quiz(
                bridge_path, bridge, quiz, prompt, folder, service
            )
            input_tokens += in_tok
            output_tokens += out_tok
            if written:
                corrected.append(written)
                local_store.resolve_uness_correction_failure(title, collected_at)
            else:
                local_store.record_uness_correction_failure(
                    bridge_folder=str(folder),
                    quiz_title=title,
                    collected_at=collected_at,
                    error_message=message or "Erreur inconnue",
                )
            if message:
                errors.append({"file": bridge_path.name, "error": message})
```

- [ ] **Step 6: Lancer toute la suite, vérifier qu'elle passe**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_gemini_autocorrect.py -v`
Expected: PASS (16 tests)

- [ ] **Step 7: Commit**

```bash
git add backend/core/uness/gemini_autocorrect.py tests/test_gemini_autocorrect.py
git commit -m "feat(uness): enregistrer/résoudre les échecs de correction dans la file d'attente"
```

---

### Task 5: `retry_failed_quiz` — relocaliser un bridge déplacé et retenter un seul quiz

**Files:**
- Modify: `backend/core/uness/gemini_autocorrect.py`
- Test: `tests/test_gemini_autocorrect.py`

**Interfaces:**
- Consumes: `local_store.get_uness_correction_failure`, `record_uness_correction_failure`, `resolve_uness_correction_failure` (Task 1) ; `import_service.TO_REVIEW_DIR`, `import_service.ARCHIVE_DIR`
- Produces: `retry_failed_quiz(failure_id: int, *, service: AIService | None = None) -> dict` — retourne `{"success": bool, "error": str | None}`

- [ ] **Step 1: Écrire les tests**

Ajouter à la fin de `tests/test_gemini_autocorrect.py` :

```python
@pytest.fixture
def _isolated_review_dirs(tmp_path, monkeypatch):
    to_review = tmp_path / "a_verifier"
    archive = tmp_path / "archives"
    to_review.mkdir()
    archive.mkdir()
    monkeypatch.setattr(import_service, "TO_REVIEW_DIR", to_review)
    monkeypatch.setattr(import_service, "ARCHIVE_DIR", archive)
    return to_review, archive


def test_retry_failed_quiz_relocates_a_bridge_still_in_a_verifier(
    _isolated_review_dirs, _isolated_verified_dir
):
    to_review, _archive = _isolated_review_dirs
    _bridge_file(to_review, title="SQI1\nTest", name="sqi1-20260801T090000Z.json")
    failure_id = local_store.record_uness_correction_failure(
        bridge_folder=str(to_review),
        quiz_title="SQI1\nTest",
        collected_at="2026-07-30T09:00:00+00:00",
        error_message="ancien échec",
    )
    service = Mock()
    service.generate.return_value = _quiz_response("SQI1\nTest")

    result = gemini_autocorrect.retry_failed_quiz(failure_id, service=service)

    assert result == {"success": True, "error": None}
    assert local_store.list_pending_uness_correction_failures() == []
    assert len(list(_isolated_verified_dir.glob("*.json"))) == 1


def test_retry_failed_quiz_relocates_a_bridge_moved_to_archives(
    _isolated_review_dirs, _isolated_verified_dir
):
    """Une fois les quiz voisins réussis, import_service déplace le dossier de
    session entier (JSON + images) vers archives/<faculté>/ — le retry doit
    suivre le bridge jusque là."""
    _to_review, archive = _isolated_review_dirs
    archived_faculty_dir = archive / "pneumologie"
    archived_faculty_dir.mkdir()
    _bridge_file(archived_faculty_dir, title="SQI1\nTest", name="a_verifier-sqi1-20260801T090000Z.json")
    failure_id = local_store.record_uness_correction_failure(
        bridge_folder="UNESS/à_vérifier/session-old",  # chemin périmé, ne doit plus être utilisé pour chercher
        quiz_title="SQI1\nTest",
        collected_at="2026-07-30T09:00:00+00:00",
        error_message="ancien échec",
    )
    service = Mock()
    service.generate.return_value = _quiz_response("SQI1\nTest")

    result = gemini_autocorrect.retry_failed_quiz(failure_id, service=service)

    assert result == {"success": True, "error": None}


def test_retry_failed_quiz_reports_a_clear_error_when_bridge_is_gone(
    _isolated_review_dirs, _isolated_verified_dir
):
    failure_id = local_store.record_uness_correction_failure(
        bridge_folder="UNESS/à_vérifier/session-old",
        quiz_title="SQI1\nTest",
        collected_at="2026-07-30T09:00:00+00:00",
        error_message="ancien échec",
    )

    result = gemini_autocorrect.retry_failed_quiz(failure_id, service=Mock())

    assert result["success"] is False
    assert "introuvable" in result["error"].lower()
    failures = local_store.list_pending_uness_correction_failures()
    assert len(failures) == 1  # toujours pending, pas perdu


def test_retry_failed_quiz_reports_unknown_failure_id(_isolated_verified_dir):
    result = gemini_autocorrect.retry_failed_quiz(999, service=Mock())

    assert result == {"success": False, "error": "Entrée introuvable"}
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_gemini_autocorrect.py -k retry_failed_quiz -v`
Expected: FAIL avec `AttributeError: module 'backend.core.uness.gemini_autocorrect' has no attribute 'retry_failed_quiz'`

- [ ] **Step 3: Implémenter `_locate_bridge` et `retry_failed_quiz`**

Ajouter à la fin de `backend/core/uness/gemini_autocorrect.py` :

```python
def _locate_bridge(quiz_title: str, collected_at: str) -> Path:
    """Cherche le bridge JSON (dans UNESS/à_vérifier puis UNESS/archives) dont
    source.collected_at correspond et dont les contents incluent quiz_title —
    un bridge peut migrer de à_vérifier/ vers archives/<faculté>/ une fois ses
    quiz voisins importés avec succès, donc les deux emplacements sont
    cherchés, à_vérifier/ en premier (le plus frais)."""
    for directory in (import_service.TO_REVIEW_DIR, import_service.ARCHIVE_DIR):
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.json")):
            if path.name.startswith("."):
                continue
            try:
                bridge = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(bridge, dict) or "contents" not in bridge:
                continue
            source = bridge.get("source", {})
            if str(source.get("collected_at", "")) != collected_at:
                continue
            titles = {item.get("title") for item in bridge.get("contents", []) if isinstance(item, dict)}
            if quiz_title in titles:
                return path
    raise FileNotFoundError(
        f"Bridge introuvable pour le quiz {quiz_title!r} (collected_at={collected_at!r})"
    )


def retry_failed_quiz(failure_id: int, *, service: AIService | None = None) -> dict:
    """Retente exactement un quiz précédemment en échec (clic manuel "Relancer"
    ou boucle de retry en arrière-plan). Relocalise son bridge (qui a pu migrer
    vers archives/ depuis l'échec), le corrige, et met à jour la ligne
    uness_correction_failures en conséquence.

    Retourne {"success": bool, "error": str | None}."""
    failure = local_store.get_uness_correction_failure(failure_id)
    if failure is None:
        return {"success": False, "error": "Entrée introuvable"}

    quiz_title = failure["quiz_title"]
    collected_at = failure["collected_at"]

    try:
        bridge_path = _locate_bridge(quiz_title, collected_at)
    except FileNotFoundError as exc:
        local_store.record_uness_correction_failure(
            bridge_folder=failure["bridge_folder"],
            quiz_title=quiz_title,
            collected_at=collected_at,
            error_message=str(exc),
        )
        return {"success": False, "error": str(exc)}

    bridge = json.loads(bridge_path.read_text(encoding="utf-8"))
    prompt = _prompt_text(bridge)
    quiz = next(
        (item for item in bridge.get("contents", []) if item.get("title") == quiz_title),
        None,
    )
    if quiz is None:
        error = f"Quiz {quiz_title!r} absent du bridge relocalisé ({bridge_path})"
        local_store.record_uness_correction_failure(
            bridge_folder=str(bridge_path.parent),
            quiz_title=quiz_title,
            collected_at=collected_at,
            error_message=error,
        )
        return {"success": False, "error": error}

    import_service.VERIFIED_DIR.mkdir(parents=True, exist_ok=True)
    written, message, _in_tok, _out_tok = _correct_one_quiz(
        bridge_path, bridge, quiz, prompt, bridge_path.parent, service
    )
    if written:
        local_store.resolve_uness_correction_failure(quiz_title, collected_at)
        return {"success": True, "error": message}

    local_store.record_uness_correction_failure(
        bridge_folder=str(bridge_path.parent),
        quiz_title=quiz_title,
        collected_at=collected_at,
        error_message=message or "Erreur inconnue",
    )
    return {"success": False, "error": message}
```

- [ ] **Step 4: Lancer toute la suite, vérifier qu'elle passe**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_gemini_autocorrect.py -v`
Expected: PASS (20 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/core/uness/gemini_autocorrect.py tests/test_gemini_autocorrect.py
git commit -m "feat(uness): retry_failed_quiz relocalise et retente un quiz en échec"
```

---

### Task 6: Retry automatique borné dans la boucle de fond

**Files:**
- Modify: `backend/core/background.py`
- Test: `tests/test_background_uness_retry.py` (nouveau)

**Interfaces:**
- Consumes: `local_store.list_pending_uness_correction_failures(due_only=True)`, `gemini_autocorrect.retry_failed_quiz` (Tasks 1 et 5)
- Produces: `_retry_pending_uness_corrections() -> None` (fonction async extraite et testable indépendamment de la boucle infinie `run_background_tasks`)

- [ ] **Step 1: Écrire le test**

Ce projet n'a pas `pytest-asyncio` installé et ne l'utilise nulle part — la
convention existante (`tests/test_robustness.py`) pour tester une coroutine
est `asyncio.run(...)` appelé depuis un `def test_...` synchrone normal.
`asyncio.to_thread` n'a pas besoin d'être mocké : il exécute réellement la
fonction (déjà mockée, elle) dans un thread, ce qui fonctionne très bien tel
quel dans un test.

```python
"""Tests for the bounded auto-retry step of UNESS correction failures in the
background sync loop (backend/core/background.py)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from backend.core import background


def test_retry_pending_uness_corrections_retries_every_due_failure():
    due = [{"id": 1}, {"id": 2}]
    with patch(
        "backend.core.reviews.local_store.list_pending_uness_correction_failures",
        return_value=due,
    ), patch("backend.core.uness.gemini_autocorrect.retry_failed_quiz") as mocked_retry:
        asyncio.run(background._retry_pending_uness_corrections())

    assert mocked_retry.call_count == 2
    mocked_retry.assert_any_call(1)
    mocked_retry.assert_any_call(2)


def test_retry_pending_uness_corrections_does_nothing_when_queue_is_empty():
    with patch(
        "backend.core.reviews.local_store.list_pending_uness_correction_failures",
        return_value=[],
    ), patch("backend.core.uness.gemini_autocorrect.retry_failed_quiz") as mocked_retry:
        asyncio.run(background._retry_pending_uness_corrections())

    mocked_retry.assert_not_called()


def test_retry_pending_uness_corrections_continues_after_one_retry_raises():
    due = [{"id": 1}, {"id": 2}]

    def _side_effect(failure_id):
        if failure_id == 1:
            raise RuntimeError("boom")
        return {"success": True, "error": None}

    with patch(
        "backend.core.reviews.local_store.list_pending_uness_correction_failures",
        return_value=due,
    ), patch(
        "backend.core.uness.gemini_autocorrect.retry_failed_quiz", side_effect=_side_effect
    ) as mocked_retry:
        asyncio.run(background._retry_pending_uness_corrections())

    assert mocked_retry.call_count == 2
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_background_uness_retry.py -v`
Expected: FAIL avec `AttributeError: module 'backend.core.background' has no attribute '_retry_pending_uness_corrections'`

- [ ] **Step 3: Ajouter la fonction et la brancher dans la boucle**

Dans `backend/core/background.py`, ajouter après `_fetch_ednpro_background` (avant `reset_autolink_cache`, vers la ligne 403) :

```python
async def _retry_pending_uness_corrections() -> None:
    """Retente en silence chaque correction UNESS en échec dont le délai de
    retry est passé (borné à 3 tentatives — cf. record_uness_correction_failure
    dans local_store.py). Une entrée qui a épuisé ses tentatives reste visible
    dans le bandeau /annales mais n'est plus reprise ici tant qu'un clic
    manuel "Relancer" ne lui redonne pas 3 tentatives fraîches."""
    from backend.core.reviews import local_store
    from backend.core.uness import gemini_autocorrect

    due = local_store.list_pending_uness_correction_failures(due_only=True)
    for failure in due:
        try:
            await asyncio.to_thread(gemini_autocorrect.retry_failed_quiz, failure["id"])
        except Exception as exc:
            logger.warning(f"Retry correction UNESS #{failure['id']} échoué : {exc}")
```

Puis, dans `run_background_tasks`, juste après le bloc "── 7. Capture EDN Pro" (les commentaires désactivés, juste avant `logger.success(f"[Cycle {_CYCLE}] Sync terminée...")`), ajouter l'appel :

```python
            # ── 8. Retry des corrections UNESS en échec (borné, silencieux) ───────
            await _retry_pending_uness_corrections()
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_background_uness_retry.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/core/background.py tests/test_background_uness_retry.py
git commit -m "feat(uness): retry automatique borné des corrections en échec dans la boucle de fond"
```

---

### Task 7: Badge sidebar sur "Annales"

**Files:**
- Modify: `frontend/cockpit_shell.py`
- Test: `tests/test_cockpit_shell.py`

**Interfaces:**
- Consumes: `local_store.count_pending_uness_correction_failures` (Task 1)
- Produces: `_uness_failures_badge() -> tuple[str, str]`

- [ ] **Step 1: Écrire le test**

Ajouter à `tests/test_cockpit_shell.py` :

```python
def test_uness_failures_badge_reads_pending_count(monkeypatch):
    monkeypatch.setattr(
        "backend.core.reviews.local_store.count_pending_uness_correction_failures", lambda: 3
    )

    assert cockpit_shell._uness_failures_badge() == ("count", "3")


def test_annales_nav_entry_has_a_dynamic_uness_failures_badge():
    from frontend.cockpit_shell import _NAV_GROUPS

    annales_entries = [
        badge
        for _group_label, items in _NAV_GROUPS
        for _glyph, label, _route, badge in items
        if label == "Annales"
    ]
    assert annales_entries == [("dynamic_count", "uness_failures")]
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_cockpit_shell.py -k uness_failures -v`
Expected: FAIL avec `AttributeError: module 'frontend.cockpit_shell' has no attribute '_uness_failures_badge'`

- [ ] **Step 3: Ajouter le badge et corriger le dispatch**

Dans `frontend/cockpit_shell.py`, juste après `_revision_badge` (qui se termine ligne 30), ajouter :

```python
def _uness_failures_badge() -> tuple[str, str]:
    """Retourne le nombre de corrections UNESS en échec pour la sidebar."""
    try:
        from backend.core.reviews.local_store import count_pending_uness_correction_failures
        count = count_pending_uness_correction_failures()
    except Exception:
        count = 0
    return ("count", str(count))


_DYNAMIC_BADGE_PROVIDERS = {
    "revisions": _revision_badge,
    "uness_failures": _uness_failures_badge,
}
```

Modifier la ligne `("▧", "Annales",   "/annales",   None),` (dans `_NAV_GROUPS`, groupe "Connaissance") en :

```python
        ("▧", "Annales",   "/annales",   ("dynamic_count", "uness_failures")),
```

Puis, dans `_nav_item`, remplacer :

```python
        elif badge and badge[0] == "dynamic_count":
            ui.label(_revision_badge()[1]).classes("cockpit-badge-count")
```

par :

```python
        elif badge and badge[0] == "dynamic_count":
            ui.label(_DYNAMIC_BADGE_PROVIDERS[badge[1]]()[1]).classes("cockpit-badge-count")
```

- [ ] **Step 4: Lancer toute la suite cockpit_shell, vérifier qu'elle passe**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_cockpit_shell.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/cockpit_shell.py tests/test_cockpit_shell.py
git commit -m "feat(uness): badge sidebar sur Annales pour les corrections en échec"
```

---

### Task 8: Bandeau + bouton "Relancer" sur la page Annales

**Files:**
- Modify: `frontend/pages/annales.py`
- Test: `tests/test_annales_page.py`

**Interfaces:**
- Consumes: `local_store.list_pending_uness_correction_failures`, `local_store.reset_uness_correction_failure_attempts` (Task 1), `gemini_autocorrect.retry_failed_quiz` (Task 5), `import_service.import_verified_directory` (existant)
- Produces: `_format_failure_row(failure: dict) -> str` (helper pur, testable sans NiceGUI)

- [ ] **Step 1: Écrire le test du helper pur**

Ajouter à `tests/test_annales_page.py` :

```python
def test_format_failure_row_includes_title_attempts_and_reason() -> None:
    from frontend.pages.annales import _format_failure_row

    row = _format_failure_row(
        {"quiz_title": "SQI1\nTest", "attempts": 2, "error_message": "Extra data: line 42"}
    )

    assert "SQI1" in row
    assert "2 tentative" in row
    assert "Extra data: line 42" in row


def test_format_failure_row_singularizes_a_single_attempt() -> None:
    from frontend.pages.annales import _format_failure_row

    row = _format_failure_row({"quiz_title": "DP1", "attempts": 1, "error_message": "erreur"})

    assert "1 tentative " in row or row.count("tentatives") == 0
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_annales_page.py -k format_failure_row -v`
Expected: FAIL avec `ImportError: cannot import name '_format_failure_row'`

- [ ] **Step 3: Ajouter `_format_failure_row` et le bandeau**

Dans `frontend/pages/annales.py`, ajouter après `_gemini_partial_failure_message` :

```python
def _format_failure_row(failure: dict) -> str:
    attempts = int(failure["attempts"])
    plural = "s" if attempts != 1 else ""
    title = str(failure["quiz_title"]).splitlines()[0]
    return f"{title} — {attempts} tentative{plural} · {failure['error_message']}"
```

Puis, dans `annales_page()`, juste après le bloc `with ui.element("div").classes("ans-topbar"): ...` (avant `all_rows = _filtered_annales()`), ajouter :

```python
            failures_column = ui.column().classes("w-full")

            def _render_failures() -> None:
                failures_column.clear()
                failures = local_store.list_pending_uness_correction_failures()
                if not failures:
                    return
                with failures_column:
                    with ui.expansion(
                        f"⚠️ {len(failures)} quiz en attente de correction", value=False
                    ).classes("w-full mb-3").props("dense"):
                        for failure in failures:
                            with ui.row().classes("w-full items-center justify-between gap-2 py-1"):
                                ui.label(_format_failure_row(failure)).classes("text-sm")

                                async def _retry(failure_id: int = failure["id"]) -> None:
                                    import asyncio
                                    from backend.core.uness import gemini_autocorrect, import_service

                                    local_store.reset_uness_correction_failure_attempts(failure_id)
                                    result = await asyncio.to_thread(
                                        gemini_autocorrect.retry_failed_quiz, failure_id
                                    )
                                    if result["success"]:
                                        ui.notify("✅ Quiz corrigé et importé.", type="positive")
                                        import_service.import_verified_directory()
                                    else:
                                        ui.notify(
                                            f"❌ Toujours en échec : {result['error']}", type="negative"
                                        )
                                    _render_failures()
                                    _render()

                                ui.button("Relancer", on_click=_retry).props(
                                    "flat dense size=sm color=primary"
                                )

            _render_failures()
```

Note : `_render_failures()` référence `_render()` (la fonction de rafraîchissement de la liste des annales), qui est définie plus bas dans `annales_page()` — comme les deux sont des closures internes à la même fonction et que `_render_failures` n'est appelée qu'après la définition complète de `_render` (au moment du clic sur "Relancer", jamais avant), l'ordre de définition dans le fichier n'a pas d'importance en Python (résolution de nom différée à l'appel).

- [ ] **Step 4: Lancer toute la suite annales_page, vérifier qu'elle passe**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_annales_page.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Vérification manuelle dans le navigateur (pas automatisable — interaction NiceGUI réelle)**

Démarrer l'app (`python main.py` ou la commande de dev habituelle), insérer manuellement une ligne dans `uness_correction_failures` via sqlite3 (ou provoquer un vrai échec Gemini), ouvrir `/annales`, vérifier :
- Le bandeau "⚠️ N quiz en attente de correction" apparaît et se déplie.
- Le badge sur "Annales" dans la sidebar affiche le même nombre.
- Cliquer "Relancer" déclenche un appel réseau (visible dans les logs), et en cas de succès simulé (mocker `AIService` momentanément si pas de clé API sous la main), le bandeau se vide et l'annale se met à jour.

- [ ] **Step 6: Commit**

```bash
git add frontend/pages/annales.py tests/test_annales_page.py
git commit -m "feat(uness): bandeau + bouton Relancer pour les corrections en échec sur /annales"
```

---

## Vérification finale

- [ ] Lancer toute la suite : `./.venv/Scripts/python.exe -m pytest tests/ -q` — aucune régression par rapport à l'état avant ce plan (7 échecs pré-existants sans rapport, déjà présents avant ce travail, sont attendus et non introduits par ce plan).
- [ ] Relire le diff complet (`git diff master~8..master` une fois les 8 tâches commitées) pour confirmer qu'aucun `TODO`/`FIXME` n'a été laissé.
