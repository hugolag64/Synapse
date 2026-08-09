# Neutralisation non destructive de la dette de reprise — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exclure les tâches et signaux antérieurs au 20 août des flux actifs sans modifier l’historique ni créer de dette synthétique.

**Architecture:** Un module pur `backend/core/reviews/reentry.py` porte la date de reprise et les filtres. `ReviewService` expose un mode `active_only` explicite ; les flux actifs l’utilisent, tandis que le détail item conserve le mode complet. La consolidation gated et Flash-Zero réutilisent les mêmes fonctions métier sans déplacer les dates persistées.

**Tech Stack:** Python 3.11, SQLite existant, Pydantic `ReviewTask`, pytest, NiceGUI.

## Execution status — 9 août 2026

- [x] Task 1 — module pur de reprise et tests de frontière.
- [x] Task 2 — mode `active_only` du `ReviewService` avec mode complet rétrocompatible.
- [x] Task 3 — branchement des flux actifs et filtrage des consolidations non gated.
- [x] Task 4 — filtrage des signaux Flash-Zero et des priorités de gain.
- [x] Task 5 — tests ciblés **66/66**, suite complète **1232/1232**, compilation Python réussie.

La vérification visuelle manuelle de l’application reste à effectuer lorsque le serveur Synapse
sera ouvert dans l’onglet local. Les prochaines tranches sont l’agrégation de toutes les échéances
futures dans Planning et la validation hybride des collèges.

## Global Constraints

- La date de reprise est exactement `2026-08-20` par défaut.
- Une échéance effective strictement antérieure à la date de reprise est neutralisée des flux actifs.
- Une échéance égale ou postérieure à la date de reprise reste active.
- Aucune ligne `review_history` n’est créée, modifiée ou supprimée.
- Les tâches neutralisées restent générables pour le détail item et les actions manuelles.
- Les consolidations déjà protégées par un gate `not_before` conservent leur comportement.
- Les signaux Flash-Zero antérieurs à la reprise ne servent pas aux nouvelles priorités ni aux nouvelles questions.
- Aucun changement visuel n’est apporté à Aujourd’hui, Planning ou à la vue thème.
- Chaque tâche se termine par des tests ciblés, une mise à jour de la roadmap et un commit.

---

### Task 1: Créer le module pur de règle de reprise

**Files:**
- Create: `backend/core/reviews/reentry.py`.
- Create: `tests/test_reentry.py`.

**Interfaces:**
- Produces `DEFAULT_STUDY_RESUME_DATE: date`.
- Produces `get_study_resume_date(preferences: Mapping[str, object] | None = None) -> date`.
- Produces `is_before_study_resume(value: date, resume_date: date | None = None) -> bool`.
- Produces `filter_active_review_tasks(tasks: Iterable[object], resume_date: date | None = None) -> list`.
- Produces `filter_post_resume_signals(signals: Iterable[Mapping], resume_date: date | None = None) -> list[dict]`.

- [ ] **Step 1: Write the failing tests**

```python
from datetime import date
from types import SimpleNamespace

from backend.core.reviews.reentry import (
    DEFAULT_STUDY_RESUME_DATE,
    filter_active_review_tasks,
    filter_post_resume_signals,
    get_study_resume_date,
)


def test_resume_date_uses_safe_default_and_valid_preference():
    assert DEFAULT_STUDY_RESUME_DATE == date(2026, 8, 20)
    assert get_study_resume_date({}) == date(2026, 8, 20)
    assert get_study_resume_date({"study_resume_date": "2026-09-01"}) == date(2026, 9, 1)


def test_invalid_resume_date_falls_back_to_default():
    assert get_study_resume_date({"study_resume_date": "not-a-date"}) == date(2026, 8, 20)


def test_active_task_filter_keeps_resume_date_and_later():
    tasks = [
        SimpleNamespace(due_date=date(2026, 8, 19)),
        SimpleNamespace(due_date=date(2026, 8, 20)),
        SimpleNamespace(due_date=date(2026, 8, 21)),
    ]
    assert filter_active_review_tasks(tasks) == tasks[1:]


def test_signal_filter_does_not_mutate_input():
    signals = [
        {"item_number": "1", "occurred_at": "2026-08-19"},
        {"item_number": "2", "occurred_at": "2026-08-20"},
    ]
    result = filter_post_resume_signals(signals)
    assert result == [signals[1]]
    assert signals[0]["occurred_at"] == "2026-08-19"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_reentry.py -q`

Expected: FAIL because `backend.core.reviews.reentry` does not exist.

- [ ] **Step 3: Implement the pure functions**

Use `date.fromisoformat` with a safe fallback, compare task `due_date` inclusively at the resume
boundary, and copy signal dictionaries into the returned list so callers cannot mutate the input.
Do not import `data_store`, SQLite, NiceGUI or any page module from this file.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_reentry.py -q`

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/core/reviews/reentry.py tests/test_reentry.py
git commit -m "feat: add pure study reentry filters"
```

### Task 2: Add the active-only ReviewService mode

**Files:**
- Modify: `backend/core/reviews/service.py` in `generate_reviews()` and `generate_all_reviews()`.
- Test: `tests/test_review_service.py` or create `tests/test_reentry_review_service.py`.

**Interfaces:**
- `generate_reviews(..., active_only: bool = False) -> list[ReviewTask]` keeps its existing default and filters only when explicitly enabled.
- `generate_all_reviews(..., active_only: bool = False) -> list[ReviewTask]` forwards the flag to both contexts.

- [ ] **Step 1: Write the failing tests**

```python
def test_generate_reviews_active_only_filters_pre_resume_tasks():
    service = ReviewService()
    course = _make_cours(days_since_lecture=32)
    with patch("backend.state.store.data_store") as mock_store:
        mock_store.cours = [course]
        mock_store.preferences = {"study_resume_date": "2026-08-20"}
        full = service.generate_reviews(context="college", history={})
        active = service.generate_reviews(context="college", history={}, active_only=True)

    assert len(full) >= len(active)
    assert any(task.due_date < date(2026, 8, 20) for task in full)
    assert all(task.due_date >= date(2026, 8, 20) for task in active)
```

Place the test beside the existing `_make_cours` helper in `tests/test_review_generation.py` or copy
that helper into the new focused test module. Patch `data_store.preferences` with the explicit
preference so the test does not depend on the process cache.

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_reentry_review_service.py -q`

Expected: FAIL because `active_only` is not accepted.

- [ ] **Step 3: Implement the opt-in filter**

Generate the virtual tasks exactly as today, then apply
`filter_active_review_tasks(tasks)` immediately before returning when `active_only` is true. Pass
the same flag from `generate_all_reviews()` to `college` and `ue`. Leave the default `False` so
manual/detail consumers keep access to neutralized tasks.

- [ ] **Step 4: Run focused and regression tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_reentry_review_service.py tests/test_review_generation.py tests/test_knowledge_no_regression.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/core/reviews/service.py tests/test_reentry_review_service.py
git commit -m "feat: support active-only review generation"
```

### Task 3: Route active application views through the central filter

**Files:**
- Modify: `frontend/pages/dashboard/_cockpit_today.py`, `_monday.py`, `todo_cockpit.py`.
- Modify: `frontend/pages/planning_cockpit.py`, `colleges_cockpit.py`, `items.py`, `frontend/cockpit_shell.py`.
- Modify: `backend/features/daily_routine.py`.
- Modify: `backend/core/reviews/consolidation.py` only for non-gated consolidation filtering.
- Test: `tests/test_reentry_active_views.py` and existing UI/service tests.

**Interfaces:**
- Active application callers invoke `review_service.generate_reviews(..., active_only=True)`.
- `course_detail_cockpit.py` remains on the default full mode so a user can inspect/reprogram a neutralized item.
- Consolidation returns no task before the resume date unless its existing `not_before` gate explicitly anchors it at or after the resume date.

- [ ] **Step 1: Write source-contract and service tests**

```python
def test_active_views_request_active_only_mode():
    for path in (
        "frontend/pages/dashboard/_cockpit_today.py",
        "frontend/pages/planning_cockpit.py",
        "frontend/pages/todo_cockpit.py",
        "backend/features/daily_routine.py",
    ):
        source = Path(path).read_text(encoding="utf-8")
        assert "active_only=True" in source


def test_consolidation_does_not_resurface_old_ungated_debt(mock_data_store):
    tasks = consolidation.get_due_consolidation_tasks(
        context="college", today=date(2026, 8, 20)
    )
    assert all(task.due_date >= date(2026, 8, 20) for task in tasks)
```

- [ ] **Step 2: Run tests to verify the contracts fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_reentry_active_views.py tests/test_consolidation.py -q`

Expected: the source contracts fail before callers are updated.

- [ ] **Step 3: Update active callers**

Add `active_only=True` to active-generation calls. Do not add it to
`frontend/pages/course_detail_cockpit.py`. In consolidation, filter only tasks whose effective due
date is before the resume date and leave existing gate behavior intact; never write a history row.

- [ ] **Step 4: Run focused tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_reentry_active_views.py tests/test_consolidation.py tests/test_cockpit_shell.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend backend/features/daily_routine.py tests/test_reentry_active_views.py
git commit -m "feat: hide pre-reentry debt from active views"
```

### Task 4: Exclude pre-reentry signals from Flash-Zero and gain priorities

**Files:**
- Modify: `backend/core/practice/flash_zero_service.py`.
- Modify: `frontend/pages/dashboard/_cockpit_today.py` signal preparation.
- Test: `tests/test_flash_zero_reentry.py` and `tests/test_edn_insights_ui.py`.

**Interfaces:**
- `FlashZeroService.generate_daily_questions()` and `get_morning_quiz()` pass their retrieved signals through `filter_post_resume_signals()` before ranking.
- Dashboard gain-item signals are filtered through the same pure function before `build_gain_items()`.
- Existing canonical questions and already stored AI questions remain untouched.

- [ ] **Step 1: Write failing tests**

```python
def test_flash_zero_priority_ignores_signals_before_resume(monkeypatch):
    prompts = []

    class FakeAI:
        def generate(self, _task, prompt, response_format="json"):
            prompts.append(prompt)
            return SimpleNamespace(text=json.dumps({
                "item_title": "Item test",
                "question_text": "Question test",
                "choices": ["A", "B"],
                "correct_idx": 0,
                "explanation": "Règle test",
                "is_zero_eliminatoire": True,
                "category": "Rang A",
            }))

    monkeypatch.setattr(
        "backend.core.practice.flash_zero_service.signals_since",
        lambda **_kwargs: [
            {"item_number": "1", "occurred_at": "2026-08-19"},
            {"item_number": "2", "occurred_at": "2026-08-20"},
        ],
    )
    store = SimpleNamespace(save_flash_zero_ai_questions=lambda _rows: None)
    FlashZeroService(store=store, ai_service=FakeAI()).generate_daily_questions(count=1)
    assert prompts and "ITEM 2" in prompts[0]
```

Import `json`, `SimpleNamespace`, and `FlashZeroService` in the focused test module. This exercises
the public generation path without adding a production-only test hook.

- [ ] **Step 2: Run focused tests to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_flash_zero_reentry.py -q`

Expected: FAIL because old signals are currently passed to the ranking function.

- [ ] **Step 3: Apply the central signal filter**

Import `filter_post_resume_signals` and filter immediately after each `signals_since()` call in
Flash-Zero. In the dashboard, filter `local_store.get_error_signals(days=30)` before passing it to
`build_gain_items()`. Preserve question persistence and canonical fallback behavior.

- [ ] **Step 4: Run focused tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_flash_zero_reentry.py tests/test_flash_zero_integration.py tests/test_edn_insights_ui.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/core/practice/flash_zero_service.py frontend/pages/dashboard/_cockpit_today.py tests/test_flash_zero_reentry.py
git commit -m "feat: ignore pre-reentry flash zero signals"
```

### Task 5: Update roadmap and verify the complete tranche

**Files:**
- Modify: `docs/ROADMAP_UX_ALGORITHMES_2026-08-09.md`.
- Modify: this plan to record execution status.
- Verify: all files changed by Tasks 1–4.

- [ ] **Step 1: Update the roadmap status**

Under Chantier 1, record that active review generation, consolidation filtering and Flash-Zero
signal filtering now use the global `study_resume_date` without rewriting history. Keep the future
planning aggregation and hybrid college confirmation as pending next slices.

- [ ] **Step 2: Run the focused suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_reentry.py tests/test_reentry_review_service.py tests/test_reentry_active_views.py tests/test_flash_zero_reentry.py tests/test_consolidation.py tests/test_flash_zero_integration.py tests/test_edn_insights_ui.py -q`

Expected: all tests pass.

- [ ] **Step 3: Run the complete suite and compile check**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m compileall -q backend frontend
```

Expected: zero test failures and zero compilation errors.

- [ ] **Step 4: Record status and commit**

```bash
git add backend frontend tests docs/ROADMAP_UX_ALGORITHMES_2026-08-09.md docs/superpowers/plans/2026-08-09-neutralisation-dette-reprise.md
git commit -m "docs: record reentry debt neutralization checkpoint"
```
