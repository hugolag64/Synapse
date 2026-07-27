# Reconnexion du retour de session Focus cockpit — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Faire passer l'intégralité du retour du wizard Focus cockpit au workflow de révision commun et ne proposer une lacune qu'après répétition d'un même signal.

**Architecture:** Un adaptateur UI-indépendant transmet les champs nommés du wizard au callback de validation commun, au lieu de les perdre dans l'appel positionnel de Focus. La persistance conserve les sessions de travail, mais remplace la création immédiate de `weak_points` par la même mécanique de proposition différée que les QCM, avec des identifiants de session préfixés par leur source.

**Tech Stack:** Python 3.11+, NiceGUI, SQLite, pytest.

## Global Constraints

- Réutiliser le wizard `open_session_feedback_dialog` existant.
- Ne créer aucune nouvelle interface ni formulaire.
- Ne pas modifier le calcul de maîtrise.
- Ne pas modifier le seuil `RECURRENCE_THRESHOLD = 2` ni la politique produit de lacunes.
- Une erreur isolée doit rester persistée comme signal, sans créer de `weak_point`.
- Les propositions de lacunes restent dans `pending_gap_proposals` et sont idempotentes pour un même item et type d'erreur.

---

## File structure

- Create: `frontend/components/session_feedback.py` — adaptateur asynchrone UI-indépendant pour la transmission du résultat complet à un callback de validation.
- Create: `tests/test_session_feedback.py` — caractérisation de l'adaptateur, sans construire de composants NiceGUI.
- Modify: `frontend/components/focus_mode_cockpit.py:203-207` — utiliser l'adaptateur au lieu de l'appel positionnel qui ignore `qcm_result`, `weak_category` et `weak_detail`.
- Modify: `backend/core/reviews/local_store.py:700-752` — persister la session sans créer immédiatement de `weak_point`, puis envoyer un signal de récurrence typé.
- Modify: `backend/core/reviews/local_store.py:2210-2284` — mutualiser la création/mise à jour de `pending_gap_proposals` pour les sources `qcm` et `study`.
- Modify: `tests/test_review_completion_service.py` — couvrir la persistance complète et l'absence de lacune immédiate.
- Create: `tests/test_recurring_study_feedback.py` — caractériser le seuil de deux signaux, l'idempotence et le format de traçabilité de la proposition.

### Task 1: Adaptateur de retour de session

**Files:**
- Create: `frontend/components/session_feedback.py`
- Create: `tests/test_session_feedback.py`
- Modify: `frontend/components/focus_mode_cockpit.py:203-207`

**Interfaces:**
- Consumes: un callback asynchrone compatible avec `DashboardState._on_done` et les champs collectés par `open_session_feedback_dialog`.
- Produces: `submit_session_feedback(on_done, task, card, *, activity_types, duration_minutes, confidence, difficulty, qcm_result, weak_category, weak_detail) -> Awaitable[None]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_session_feedback.py` with a recording callback. It must assert named forwarding of every field that the Focus path currently loses.

```python
import pytest

from frontend.components.session_feedback import submit_session_feedback


@pytest.mark.asyncio
async def test_submit_session_feedback_forwards_full_wizard_result():
    received = {}

    async def on_done(task, card, **feedback):
        received["task"] = task
        received["card"] = card
        received.update(feedback)

    task = object()
    card = object()
    await submit_session_feedback(
        on_done, task, card,
        activity_types=["révision", "qcm"], duration_minutes=25,
        confidence=2, difficulty="difficile", qcm_result="raté",
        weak_category="raisonnement", weak_detail="Oubli du diagnostic différentiel",
    )

    assert received == {
        "task": task, "card": card, "activity_types": ["révision", "qcm"],
        "duration_minutes": 25, "confidence": 2, "difficulty": "difficile",
        "qcm_result": "raté", "weak_category": "raisonnement",
        "weak_detail": "Oubli du diagnostic différentiel",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_session_feedback.py::test_submit_session_feedback_forwards_full_wizard_result -q`

Expected: FAIL during collection because `frontend.components.session_feedback` does not exist.

- [ ] **Step 3: Write minimal implementation**

Create `frontend/components/session_feedback.py` with only the adapter below. Keep the protocol permissive because existing page callbacks are closures with compatible keyword parameters.

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


async def submit_session_feedback(
    on_done: Callable[..., Awaitable[None]] | None,
    task: Any,
    card: Any,
    *,
    activity_types: list | None = None,
    duration_minutes: int | None = None,
    confidence: int | None = None,
    difficulty: str | None = None,
    qcm_result: str | None = None,
    weak_category: str | None = None,
    weak_detail: str | None = None,
) -> None:
    if on_done is None:
        return
    await on_done(
        task, card,
        activity_types=activity_types,
        duration_minutes=duration_minutes,
        confidence=confidence,
        difficulty=difficulty,
        qcm_result=qcm_result,
        weak_category=weak_category,
        weak_detail=weak_detail,
    )
```

Then replace the Focus callback body with named forwarding and preserve its navigation only after successful completion:

```python
from frontend.components.session_feedback import submit_session_feedback

async def _cockpit_on_done(task, card, activity_types=None, duration_minutes=None,
                           confidence=None, difficulty=None, **feedback):
    await submit_session_feedback(
        _on_done, task, card,
        activity_types=activity_types, duration_minutes=duration_minutes,
        confidence=confidence, difficulty=difficulty, **feedback,
    )
    _nav(1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_session_feedback.py::test_submit_session_feedback_forwards_full_wizard_result -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add -- frontend/components/session_feedback.py frontend/components/focus_mode_cockpit.py tests/test_session_feedback.py
git commit -m "fix: forward full focus session feedback"
```

### Task 2: Proposition différée pour les signaux de session

**Files:**
- Modify: `backend/core/reviews/local_store.py:700-752`
- Modify: `backend/core/reviews/local_store.py:2210-2284`
- Modify: `tests/test_review_completion_service.py`
- Create: `tests/test_recurring_study_feedback.py`

**Interfaces:**
- Consumes: les colonnes `study_sessions.item_number`, `weak_category`, `weak_detail` et la constante `RECURRENCE_THRESHOLD`.
- Produces: `check_and_propose_recurring_study_feedback(item_number, error_type, new_session_id, course_title="", course_id="") -> list[int]` et des `pending_gap_proposals.session_ids` au format JSON de chaînes préfixées (`"study:<id>"` ou `"qcm:<id>"`).

- [ ] **Step 1: Write the failing tests**

Extend `tests/test_review_completion_service.py` so qu'une session détaillée ne crée plus directement de `weak_points` :

```python
def test_complete_review_records_feedback_without_creating_immediate_weak_point():
    complete_review(
        _task(), qcm_result="raté", weak_category="raisonnement",
        weak_detail="Oubli du diagnostic différentiel",
    )

    with local_store._conn() as con:
        weak_points = con.execute("SELECT COUNT(*) FROM weak_points").fetchone()[0]
    session = _sessions("course-1")

    assert session[0]["qcm_result"] == "raté"
    assert session[0]["weak_category"] == "raisonnement"
    assert session[0]["weak_detail"] == "Oubli du diagnostic différentiel"
    assert weak_points == 0
```

Create `tests/test_recurring_study_feedback.py` with the same isolated SQLite fixture as `test_review_completion_service.py`, then add this test:

```python
def test_second_matching_study_feedback_creates_one_pending_gap_proposal():
    for detail in ("Erreur 1", "Erreur 2"):
        local_store.add_study_session(
            "course-1", course_title="Cardiologie", item_number="75",
            qcm_result="raté", weak_category="raisonnement", weak_detail=detail,
        )

    proposals = local_store.get_pending_proposals()
    with local_store._conn() as con:
        weak_points = con.execute("SELECT COUNT(*) FROM weak_points").fetchone()[0]

    assert len(proposals) == 1
    assert proposals[0]["item_number"] == "75"
    assert proposals[0]["error_type"] == "raisonnement"
    assert proposals[0]["occurrence_count"] == 2
    assert weak_points == 0
```

Add an idempotence test by calling `check_and_propose_recurring_study_feedback` again with the second session id and asserting that one proposal remains and its `session_ids` JSON contains each `study:<id>` once.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_review_completion_service.py::test_complete_review_records_feedback_without_creating_immediate_weak_point tests/test_recurring_study_feedback.py -q`

Expected: FAIL because `add_study_session` currently calls `add_weak_point` after any non-empty `weak_detail`, and no recurrence checker for study feedback exists.

- [ ] **Step 3: Write minimal implementation**

In `add_study_session`, retain the insert and returned SQLite id, remove the `add_weak_point(...)` block, then call the new checker only when both `item_number` and a non-empty normalized `weak_category` are present. Treat `"aucune"` and an empty category as no recurrence signal.

```python
category = (weak_category or "").strip()
if item_number and category and category.casefold() != "aucune":
    check_and_propose_recurring_study_feedback(
        item_number=item_number,
        error_type=category,
        new_session_id=session_id,
        course_title=course_title,
        course_id=course_id,
    )
return session_id
```

Extract the insert/update portion of `check_and_propose_recurring_gaps` into a private helper:

```python
def _upsert_recurring_gap_proposal(
    *, item_number: str, error_type: str, source_session_ids: set[str],
    occurrence_count: int, course_title: str, course_id: str,
) -> list[int]:
    # Return [] below RECURRENCE_THRESHOLD; otherwise update the single pending
    # proposal for (item_number, error_type), preserving a JSON list of tagged ids.
```

Make the QCM checker pass `{"qcm:<id>"}` ids and keep its current query over `qcm_sessions`. The new study checker queries distinct `study_sessions.id` for the exact same `item_number` and normalized `weak_category`, builds `{"study:<id>"}` ids, and delegates to the helper. When reading pre-existing integer `session_ids`, normalize each as `"qcm:<id>"` before merging so old proposals remain usable and mixed Python types are never sorted together.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_review_completion_service.py tests/test_recurring_study_feedback.py -q`

Expected: PASS. Then run the existing QCM and weak-point tests:

Run: `python -m pytest tests/test_local_store.py tests/test_knowledge_no_regression.py tests/test_weak_points_sync.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add -- backend/core/reviews/local_store.py tests/test_review_completion_service.py tests/test_recurring_study_feedback.py
git commit -m "fix: defer session weak points until recurrence"
```

### Task 3: Vérification de la reconnexion complète

**Files:**
- Modify: `tests/test_session_feedback.py`
- Modify: `tests/test_recurring_study_feedback.py`

**Interfaces:**
- Consumes: `submit_session_feedback`, `complete_review`, `local_store.get_pending_proposals`.
- Produces: une preuve de non-régression du chemin Focus → callback commun → session SQLite → proposition différée.

- [ ] **Step 1: Write the failing integration-style test**

In `tests/test_session_feedback.py`, add a callback réel qui appelle `complete_review`, puis invoque l'adaptateur avec le retour Focus :

```python
@pytest.mark.asyncio
async def test_focus_feedback_reaches_review_completion_without_immediate_weak_point():
    task = _task()

    async def on_done(task, card, **feedback):
        complete_review(task, **feedback)

    await submit_session_feedback(
        on_done, task, object(), activity_types=["qcm"], duration_minutes=15,
        confidence=2, difficulty="difficile", qcm_result="raté",
        weak_category="raisonnement", weak_detail="Confusion de prise en charge",
    )

    assert _sessions("course-1")[0]["weak_detail"] == "Confusion de prise en charge"
    assert local_store.get_pending_proposals() == []
```

Reuse the isolated database fixture by moving it to `tests/conftest.py` only if doing so does not change the behavior of existing tests; otherwise duplicate the small fixture in this test module.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_session_feedback.py::test_focus_feedback_reaches_review_completion_without_immediate_weak_point -q`

Expected: FAIL before Task 1 and Task 2 are both implemented; after their commits it must pass without production changes in this task.

- [ ] **Step 3: Add only missing test setup**

Do not change production code. Add the minimal local `_task`, `_sessions` and isolated-db fixture necessary for the test to call the real `complete_review` service.

- [ ] **Step 4: Run targeted and full verification**

Run: `python -m pytest tests/test_session_feedback.py tests/test_review_completion_service.py tests/test_recurring_study_feedback.py -q`

Expected: PASS.

Run: `python -m pytest -q`

Expected: all tests outside the pre-existing LiSA scraper contract failures pass; report the exact count and preserve those failures unchanged unless their contract is separately selected.

- [ ] **Step 5: Commit**

```powershell
git add -- tests/test_session_feedback.py tests/test_recurring_study_feedback.py
git commit -m "test: characterize focus feedback reconnection"
```

## Plan self-review

- **Spec coverage:** Task 1 covers the shared adapter and complete Focus forwarding. Task 2 covers persistence, the existing threshold of two, one pending proposal and no direct lacune. Task 3 proves the end-to-end non-UI path and runs the regression suite.
- **Placeholder scan:** no `TODO`, `TBD`, vague error-handling instruction or implicit test is left in the tasks.
- **Type consistency:** all callback fields use the existing names from `open_session_feedback_dialog` and `complete_review`; recurrence functions return `list[int]`; tagged session identifiers are consistently strings.

