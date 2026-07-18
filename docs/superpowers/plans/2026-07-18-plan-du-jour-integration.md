# Plan du jour Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Dashboard's RETARD/AUJOURD'HUI list and a new "Plan du jour" section on the To Do page both surface Consolidation tasks and active lacunes, validated through the same shared `open_session_feedback_dialog` wizard already used everywhere else.

**Architecture:** No new persistence layer — Dashboard and To Do both live-query the same three existing sources (`review_service.generate_reviews`, `planning_service.plan_consolidation`, `local_store.get_all_weak_points_table`) that Planning's Journée/Consolidation tabs already use. A new `weak_point_to_task()` adapter turns a `weak_points` SQLite row into a `ReviewTask` so lacunes can flow through the same wizard/card components as reviews and consolidation. Validation callbacks branch on `task.review_type` to call the right backend function (`mark_done` / `mark_consolidation_done` / `resolve_weak_point`).

**Tech Stack:** Python 3.13, NiceGUI (frontend), SQLite (`data/synapse_local.db`), pydantic (`ReviewTask`), pytest (unittest.TestCase style + `isolated_db` fixture pattern from `tests/test_consolidation.py`).

## Global Constraints

- No Notion writes for lacune or consolidation validation — only the existing J3/J7/J14/J30 `mark_done` path syncs Notion `nb_lectures` counters (unchanged); consolidation and lacune skip that sync entirely.
- `context` is always `"college"` for lacune tasks (lacunes don't distinguish collège/UE) — same constraint the consolidation feature already follows.
- Reuse `open_session_feedback_dialog` (`frontend/pages/dashboard/_dialogs.py:205`) as-is for all three task types — no parallel dialog.
- Reuse `_consolidation_card`'s visual pattern (`frontend/pages/planning.py:127`) for the new To Do section — same `border-l-4`/`rounded-xl` card shape, don't invent a new component style.
- Lacune cards get a "Valider" action only — no "Passer"/"Ignorer" (there is no meaningful postpone/ignore semantics for a `weak_points` row). Lacunes only ever appear in To Do's "Plan du jour" (Task 5) — they are not merged into the Dashboard's RETARD/AUJOURD'HUI list (Task 3 merges consolidation tasks only; the Dashboard already has its own separate "Lacune du Jour" widget).
- Every new SQLite-adjacent helper goes through existing `local_store.py` functions (`resolve_weak_point`, `get_all_weak_points_table`) — no new tables, no new raw SQL.

---

## File Structure

- **Modify** `backend/core/reviews/models.py` — add `"lacune"` to the `ReviewType` Literal.
- **Create** `backend/core/reviews/lacune_adapter.py` — `weak_point_to_task(row) -> ReviewTask`.
- **Create** `tests/test_lacune_adapter.py` — covers `weak_point_to_task`.
- **Modify** `frontend/pages/dashboard/_dialogs.py` — add a `"lacune"` preset branch in `open_session_feedback_dialog`.
- **Modify** `frontend/pages/dashboard/_reviews.py` — merge consolidation tasks into `all_tasks` in `rebuild_all()` (no automated test — `rebuild_all` is a NiceGUI-rendering function with no existing unit-test precedent in this project; verified manually in Task 6).
- **Modify** `frontend/pages/dashboard/__init__.py` — branch `_on_done`/`_on_postpone`/`_on_ignore` on `task.review_type`.
- **Modify** `frontend/pages/todo.py` — new "Plan du jour" section: a pure aggregation function (unit-testable) plus its NiceGUI rendering.
- **Create** `tests/test_todo_plan_du_jour.py` — covers the aggregation function.

---

### Task 1: `lacune_adapter.py` — turn a weak_point row into a `ReviewTask`

**Files:**
- Modify: `backend/core/reviews/models.py:15`
- Create: `backend/core/reviews/lacune_adapter.py`
- Test: `tests/test_lacune_adapter.py`

**Interfaces:**
- Consumes: `backend.core.reviews.local_store.get_all_weak_points_table` row shape (sqlite3.Row with keys `id, course_id, course_title, item_number, category, detail, severity, status, source_session_id, created_at, resolved_at`, `backend/core/reviews/local_store.py:144-156`); `data_store.cours` (list of `Cours`, each with `.id`, `.college`).
- Produces: `weak_point_to_task(row) -> ReviewTask` — used by Task 5 (To Do's "Plan du jour"; lacunes do not appear on the Dashboard, see Task 4's note). `ReviewTask.id` is `f"lacune_{row['id']}"`; callers recover the weak_point id via `int(task.id.removeprefix("lacune_"))`.

- [ ] **Step 1: Add `"lacune"` to the `ReviewType` Literal**

In `backend/core/reviews/models.py`, change line 15:

```python
ReviewType   = Literal["J3", "J7", "J14", "J30", "bonus", "qcm_error", "manuel", "consolidation"]
```

to:

```python
ReviewType   = Literal["J3", "J7", "J14", "J30", "bonus", "qcm_error", "manuel", "consolidation", "lacune"]
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_lacune_adapter.py`:

```python
"""Tests unitaires — adaptateur weak_point -> ReviewTask."""
import datetime
from unittest.mock import MagicMock, patch

from backend.core.notion.models import Cours


def _mock_cours(id, title, college):
    c = MagicMock(spec=Cours)
    c.id = id
    c.title = title
    c.college = college
    return c


def _mock_wp_row(id=1, course_id="course-1", course_title="Cours test",
                  item_number="42", detail="Confusion IRM/TDM avant PL"):
    return {
        "id": id,
        "course_id": course_id,
        "course_title": course_title,
        "item_number": item_number,
        "category": "Examens",
        "detail": detail,
        "severity": 3,
        "status": "active",
        "source_session_id": None,
        "created_at": "2026-07-18T10:00:00",
        "resolved_at": None,
    }


@patch('backend.state.store.data_store')
def test_weak_point_to_task_cours_trouve(mock_data_store):
    from backend.core.reviews.lacune_adapter import weak_point_to_task

    mock_data_store.cours = [_mock_cours("course-1", "Cours test", ["Neurologie 🧠"])]
    row = _mock_wp_row()

    task = weak_point_to_task(row)

    assert task.id == "lacune_1"
    assert task.course_id == "course-1"
    # course_title is set to the lacune's own text (row["detail"]), not the
    # course's title — the card's headline should be "what's wrong", not
    # the course name (see ReviewTask.label = f"ITEM {item_number} – {course_title}").
    assert task.course_title == "Confusion IRM/TDM avant PL"
    assert task.item_number == "42"
    assert task.college == ["Neurologie 🧠"]
    assert task.context == "college"
    assert task.review_type == "lacune"
    assert task.label == "ITEM 42 – Confusion IRM/TDM avant PL"
    assert task.theoretical_due_date == datetime.date.today()
    assert task.due_date == datetime.date.today()


@patch('backend.state.store.data_store')
def test_weak_point_to_task_cours_introuvable(mock_data_store):
    from backend.core.reviews.lacune_adapter import weak_point_to_task

    mock_data_store.cours = []  # course_id ne matche aucun cours chargé
    row = _mock_wp_row(id=2, course_id="orphan-course")

    task = weak_point_to_task(row)

    assert task.id == "lacune_2"
    assert task.college == []
    assert task.context == "college"
    assert task.course_id == "orphan-course"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_lacune_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.core.reviews.lacune_adapter'`

- [ ] **Step 4: Write the implementation**

Create `backend/core/reviews/lacune_adapter.py`:

```python
"""
lacune_adapter.py — Synapse
----------------------------
Convertit une ligne de la table weak_points en ReviewTask, pour que les
lacunes actives puissent traverser le même pipeline carte/assistant que
les révisions et la consolidation (Dashboard RETARD/AUJOURD'HUI, To Do).

Pas d'écriture Notion, pas de nouvelle table — pur adaptateur en mémoire.
"""
from __future__ import annotations

import datetime

from backend.core.reviews.models import ReviewTask


def weak_point_to_task(row) -> ReviewTask:
    """
    Construit une ReviewTask virtuelle (review_type="lacune") à partir d'une
    ligne weak_points (dict ou sqlite3.Row — accès par clé dans les deux cas).

    Le libellé affiché est le texte de la lacune (row["detail"]), pas le
    titre du cours : c'est ce qui doit apparaître en premier sur la carte.
    """
    from backend.state.store import data_store

    course = next((c for c in data_store.cours if c.id == row["course_id"]), None)
    college = list(course.college) if course is not None else []

    today = datetime.date.today()
    return ReviewTask(
        id=f"lacune_{row['id']}",
        course_id=row["course_id"],
        course_title=row["detail"],
        item_number=row["item_number"] or None,
        college=college,
        context="college",
        theoretical_due_date=today,
        due_date=today,
        review_type="lacune",
        status="todo",
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_lacune_adapter.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/core/reviews/models.py backend/core/reviews/lacune_adapter.py tests/test_lacune_adapter.py
git commit -m "feat(reviews): add lacune_adapter to bridge weak_points into ReviewTask"
```

---

### Task 2: `open_session_feedback_dialog` — preset for `review_type == "lacune"`

**Files:**
- Modify: `frontend/pages/dashboard/_dialogs.py:210-216`

**Interfaces:**
- Consumes: `ReviewTask.review_type` (Task 1).
- Produces: no new function — extends the existing preset `if/elif/else` so a lacune card opens with sensible defaults instead of falling into the generic `else` branch.

- [ ] **Step 1: Modify the preset branch**

In `frontend/pages/dashboard/_dialogs.py`, change:

```python
    if task.review_type == "bonus":
        _acts, _dur, _conf, _diff, _qcm = ["lecture"], 30, 3, "moyen", None
    elif task.review_type == "qcm_error":
        _acts, _dur, _conf, _diff, _qcm = ["qcm", "correction"], 20, 2, "difficile", "raté"
    else:
        _acts, _dur, _conf, _diff, _qcm = ["révision"], 20, 3, "moyen", None
```

to:

```python
    if task.review_type == "bonus":
        _acts, _dur, _conf, _diff, _qcm = ["lecture"], 30, 3, "moyen", None
    elif task.review_type == "qcm_error":
        _acts, _dur, _conf, _diff, _qcm = ["qcm", "correction"], 20, 2, "difficile", "raté"
    elif task.review_type == "lacune":
        _acts, _dur, _conf, _diff, _qcm = ["correction"], 15, 3, "moyen", None
    else:
        _acts, _dur, _conf, _diff, _qcm = ["révision"], 20, 3, "moyen", None
```

- [ ] **Step 2: Verify no test regression**

This module has no dedicated unit test (NiceGUI dialog rendering isn't unit-tested anywhere in this project). Verify the file still imports cleanly:

Run: `python -c "import ast; ast.parse(open('frontend/pages/dashboard/_dialogs.py', encoding='utf-8').read())"`
Expected: no output, exit code 0

- [ ] **Step 3: Commit**

```bash
git add frontend/pages/dashboard/_dialogs.py
git commit -m "feat(dashboard): add lacune preset to session feedback dialog"
```

---

### Task 3: Dashboard `rebuild_all()` — merge consolidation tasks into RETARD/AUJOURD'HUI

**Files:**
- Modify: `frontend/pages/dashboard/_reviews.py:862-876`

**Interfaces:**
- Consumes: `planning_service.plan_consolidation()` (`backend/core/planning/service.py:238`, already implemented — returns `(selected: list[ReviewTask], skipped: list[ReviewTask])`); `review_service.get_urgent_tasks`/`get_today_tasks` (`backend/core/reviews/service.py:285,303` — generic on `t.due_date`, no `review_type` dependency).
- Produces: `all_tasks` inside `rebuild_all()` now includes consolidation tasks before the college filter and before the urgent/today split — no new public function, this task only changes `rebuild_all`'s internals.

Why `all_tasks` (not appending straight to `urgent`/`today_tasks` after they're computed): the Dashboard's college filter (`frontend/pages/dashboard/_reviews.py:869-873`) runs on `all_tasks` before `urgent`/`today_tasks` are derived. Merging consolidation tasks in earlier means they pass through the same filter as every other task — merging them after would silently bypass it.

**No automated test for this task.** `rebuild_all()` is a NiceGUI-rendering function (clears/rebuilds real `ui.column()` elements, calls `render_college_chips`, `render_review_row`, the banner, etc.) — there is no precedent anywhere in this project for unit-testing a function like this outside of a live page context, and `rebuild_all` itself has no pre-existing test to extend. Introducing a NiceGUI test harness is out of scope for this plan (YAGNI — the project has managed without one for every prior Planning/Dashboard feature, verified manually instead). Verified manually in Task 6, Steps 2-4.

- [ ] **Step 1: Implement the merge**

In `frontend/pages/dashboard/_reviews.py`, change:

```python
    history   = local_store.get_all_history()
    all_tasks = review_service.generate_reviews(
        context=state.review_context, history=history
    )
    all_tasks = externat_service.apply_stage_boost(all_tasks)

    render_college_chips(state, all_tasks)
```

to:

```python
    history   = local_store.get_all_history()
    all_tasks = review_service.generate_reviews(
        context=state.review_context, history=history
    )
    all_tasks = externat_service.apply_stage_boost(all_tasks)

    from backend.core.planning.service import planning_service
    consolidation_selected, _ = planning_service.plan_consolidation()
    all_tasks = all_tasks + consolidation_selected

    render_college_chips(state, all_tasks)
```

- [ ] **Step 2: Verify the file still parses and run the full test suite**

Run: `python -c "import ast; ast.parse(open('frontend/pages/dashboard/_reviews.py', encoding='utf-8').read())"`
Expected: no output, exit code 0

Run: `python -m pytest -q`
Expected: same pass/fail counts as before this task (4 pre-existing unrelated failures in `tests/test_lisa_scraper.py` are expected and not caused by this change) — this task changes no tested code path, only `rebuild_all`'s internals.

- [ ] **Step 3: Commit**

```bash
git add frontend/pages/dashboard/_reviews.py
git commit -m "feat(dashboard): merge consolidation tasks into RETARD/AUJOURD'HUI"
```

---

### Task 4: Dashboard action callbacks — branch on `review_type` for consolidation

**Files:**
- Modify: `frontend/pages/dashboard/__init__.py:135-257`

**Interfaces:**
- Consumes: `local_store.mark_consolidation_done`, `local_store.add_study_session` — both already existing.
- Produces: `_on_done`/`_on_postpone`/`_on_ignore` now handle `review_type == "consolidation"` in addition to the existing J3-J30/bonus/qcm_error path. No signature changes — same 3 functions, same call site at `rebuild_all(state, _on_done, _on_postpone, _on_ignore, _on_done)` (`__init__.py:260`, unchanged).

Note: lacune tasks are **not** handled here. Task 3 only merges *consolidation* tasks into the Dashboard's `all_tasks` (`review_type="lacune"` tasks never reach `_on_done`/`_on_postpone`/`_on_ignore` on the Dashboard — the Dashboard already has its own separate "Lacune du Jour" widget, `frontend/pages/dashboard/_agenda.py`, untouched by this plan). Lacune validation only happens through the To Do page's own `_validate` closure (Task 5), which is self-contained and doesn't call these functions. Adding a `"lacune"` branch here would be dead code.

This task has no dedicated automated test — `_on_done`/`_on_postpone`/`_on_ignore` are closures defined inside the page function and call `local_store`/`ui.notify`/`asyncio` directly; there's no existing precedent in this project for unit-testing NiceGUI page closures (same limitation noted in the Consolidation plan for `frontend/pages/planning.py`'s equivalent functions). Verify via the manual steps in Task 6.

- [ ] **Step 1: Branch `_on_done` on `review_type`**

In `frontend/pages/dashboard/__init__.py`, change the body of `_on_done` (currently lines 146-223) from:

```python
            try:
                card.classes(add="ring-2 ring-green-400 bg-green-50 dark:bg-green-900/20 transition-all duration-200")
            except Exception:
                pass
            await asyncio.sleep(0.2)
            try:
                card.classes(
                    add="opacity-0 scale-95",
                    remove="ring-2 ring-green-400 bg-green-50 dark:bg-green-900/20",
                )
            except Exception:
                pass
            await asyncio.sleep(0.3)

            local_store.mark_done(
                task_id=task.id,
                course_id=task.course_id,
                context=task.context,
                review_type=task.review_type,
                theoretical_due_date=task.theoretical_due_date,
                course_title=task.course_title,
                item_number=task.item_number or "",
                difficulty=difficulty,
                confidence=confidence,
            )
            state.done_today_count += 1

            local_store.add_study_session(
                course_id=task.course_id,
                course_title=task.course_title,
                item_number=task.item_number or "",
                context=task.context,
                activity_types=activity_types or ["révision"],
                duration_minutes=duration_minutes,
                confidence=confidence,
                difficulty=difficulty,
                qcm_result=qcm_result,
                weak_category=weak_category,
                weak_detail=weak_detail,
            )

            _do_rebuild()
            ui.notify(f"✓ Révisé : {task.course_title}", type="positive")

            # PP-07 — Bilan quand toutes les urgentes sont faites
            try:
                _new_load = compute_daily_load(
                    review_service.get_urgent_tasks(
                        review_service.generate_reviews(
                            context=state.review_context,
                            history=local_store.get_all_history(),
                        )
                    ),
                    [],
                )
                if _new_load["urgent_count"] == 0 and state.done_today_count >= 1 and not _bilan_shown["shown"]:
                    _bilan_shown["shown"] = True
                    show_bilan_session(state, state.done_today_count)
            except Exception:
                pass

            # Sync Notion en arrière-plan
            async def _sync():
                c = next((x for x in data_store.cours if x.id == task.course_id), None)
                if not c:
                    return
                if task.context == "college":
                    ok = await notion_service.increment_lecture_college(c.id, c.nb_lectures)
                    if ok:
                        c.nb_lectures += 1
                else:
                    ok = await notion_service.increment_lecture_ue(c.id, c.nb_lectures_ue)
                    if ok:
                        c.nb_lectures_ue += 1
                if ok:
                    data_store.save_to_disk()

            asyncio.create_task(_sync())
```

to:

```python
            try:
                card.classes(add="ring-2 ring-green-400 bg-green-50 dark:bg-green-900/20 transition-all duration-200")
            except Exception:
                pass
            await asyncio.sleep(0.2)
            try:
                card.classes(
                    add="opacity-0 scale-95",
                    remove="ring-2 ring-green-400 bg-green-50 dark:bg-green-900/20",
                )
            except Exception:
                pass
            await asyncio.sleep(0.3)

            if task.review_type == "consolidation":
                local_store.mark_consolidation_done(
                    course_id=task.course_id,
                    context=task.context,
                    theoretical_due_date=task.theoretical_due_date,
                    course_title=task.course_title,
                    item_number=task.item_number or "",
                    confidence=confidence or 3,
                    difficulty=difficulty,
                )
            else:
                local_store.mark_done(
                    task_id=task.id,
                    course_id=task.course_id,
                    context=task.context,
                    review_type=task.review_type,
                    theoretical_due_date=task.theoretical_due_date,
                    course_title=task.course_title,
                    item_number=task.item_number or "",
                    difficulty=difficulty,
                    confidence=confidence,
                )
            state.done_today_count += 1

            local_store.add_study_session(
                course_id=task.course_id,
                course_title=task.course_title,
                item_number=task.item_number or "",
                context=task.context,
                activity_types=activity_types or ["révision"],
                duration_minutes=duration_minutes,
                confidence=confidence,
                difficulty=difficulty,
                qcm_result=qcm_result,
                weak_category=weak_category,
                weak_detail=weak_detail,
            )

            _do_rebuild()
            ui.notify(f"✓ Révisé : {task.course_title}", type="positive")

            # PP-07 — Bilan quand toutes les urgentes sont faites
            try:
                _new_load = compute_daily_load(
                    review_service.get_urgent_tasks(
                        review_service.generate_reviews(
                            context=state.review_context,
                            history=local_store.get_all_history(),
                        )
                    ),
                    [],
                )
                if _new_load["urgent_count"] == 0 and state.done_today_count >= 1 and not _bilan_shown["shown"]:
                    _bilan_shown["shown"] = True
                    show_bilan_session(state, state.done_today_count)
            except Exception:
                pass

            # Sync Notion en arrière-plan (uniquement pour les révisions J3-J30 classiques —
            # la consolidation ne touche jamais aux compteurs Notion)
            if task.review_type != "consolidation":
                async def _sync():
                    c = next((x for x in data_store.cours if x.id == task.course_id), None)
                    if not c:
                        return
                    if task.context == "college":
                        ok = await notion_service.increment_lecture_college(c.id, c.nb_lectures)
                        if ok:
                            c.nb_lectures += 1
                    else:
                        ok = await notion_service.increment_lecture_ue(c.id, c.nb_lectures_ue)
                        if ok:
                            c.nb_lectures += 1
                    if ok:
                        data_store.save_to_disk()

                asyncio.create_task(_sync())
```

- [ ] **Step 2: Confirm `_on_postpone`/`_on_ignore` need no changes**

`local_store.postpone`/`local_store.ignore` (called by `_on_postpone`/`_on_ignore`, `frontend/pages/dashboard/__init__.py:225-257`) are already generic on `review_type` — no special-casing needed. This is already proven working for `review_type="consolidation"` by `frontend/pages/planning.py`'s own `_on_postpone` (shipped in the prior Consolidation feature). Read `frontend/pages/dashboard/__init__.py:225-257` and confirm neither function references anything specific to J3-J30 review types (task_id/course_id/context/review_type/theoretical_due_date are all present on every `ReviewTask` regardless of type) — no code change required for this step.

- [ ] **Step 3: Verify the file still parses and imports cleanly**

Run: `python -c "import ast; ast.parse(open('frontend/pages/dashboard/__init__.py', encoding='utf-8').read())"`
Expected: no output, exit code 0

- [ ] **Step 4: Run the full test suite**

Run: `python -m pytest -q`
Expected: no new failures versus Task 3's baseline.

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/dashboard/__init__.py
git commit -m "feat(dashboard): route consolidation/lacune validation through their own backends"
```

---

### Task 5: To Do — new "Plan du jour" section

**Files:**
- Modify: `frontend/pages/todo.py`
- Test: `tests/test_todo_plan_du_jour.py` (new)

**Interfaces:**
- Consumes: `review_service.generate_reviews` + `get_urgent_tasks`/`get_today_tasks`; `planning_service.plan_consolidation()`; `local_store.get_all_weak_points_table(status_filter="active")`; `lacune_adapter.weak_point_to_task` (Task 1); `open_session_feedback_dialog` (Task 2's updated presets apply here too).
- Produces: `_gather_plan_du_jour(context: str = "college") -> list[ReviewTask]` — a pure, synchronous, unit-testable function (no NiceGUI calls) that any future caller can reuse; `_render_plan_du_jour_block(container: ui.column) -> None` — the NiceGUI rendering, called from `_render_content` only.

- [ ] **Step 1: Write the failing test**

Create `tests/test_todo_plan_du_jour.py`:

```python
"""Tests unitaires — agrégation du bloc Plan du jour (To Do)."""
import datetime
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import backend.core.reviews.local_store as ls
    import backend.core.knowledge.store as ks

    test_db = tmp_path / "test.db"
    monkeypatch.setattr(ls, "DB_PATH", test_db)
    monkeypatch.setattr(ls, "_DB", None)
    ls.init_db()
    ks.init_knowledge_tables()
    yield
    if ls._DB is not None:
        ls._DB.close()
    monkeypatch.setattr(ls, "_DB", None)


@patch('backend.core.planning.service.planning_service.plan_consolidation')
@patch('backend.core.reviews.service.review_service.generate_reviews')
def test_gather_plan_du_jour_agrege_les_3_sources(mock_generate, mock_plan_consolidation):
    from frontend.pages.todo import _gather_plan_du_jour
    from backend.core.reviews.models import ReviewTask
    import backend.core.reviews.local_store as ls

    today = datetime.date.today()
    review_task = ReviewTask(
        id="rev-1", course_id="course-1", course_title="Cours révision",
        theoretical_due_date=today, due_date=today, review_type="J3",
    )
    mock_generate.return_value = [review_task]

    consolidation_task = ReviewTask(
        id="cons-1", course_id="course-2", course_title="Cours consolidé",
        theoretical_due_date=today, due_date=today, review_type="consolidation",
    )
    mock_plan_consolidation.return_value = ([consolidation_task], [])

    ls.add_weak_point_full(
        course_id="course-3", detail="Oubli hémocultures avant ATB",
        course_title="Cours lacune", item_number="99",
    )

    items = _gather_plan_du_jour()

    ids = {t.id for t in items}
    assert "rev-1" in ids
    assert "cons-1" in ids
    assert any(t.review_type == "lacune" and t.course_title == "Oubli hémocultures avant ATB" for t in items)
    assert len(items) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_todo_plan_du_jour.py -v`
Expected: FAIL with `ImportError: cannot import name '_gather_plan_du_jour'`

- [ ] **Step 3: Implement `_gather_plan_du_jour`**

In `frontend/pages/todo.py`, add this function near the top, after the existing helper functions (after `_week_dates` at line 76, before `_get_routine_summary` at line 81):

```python
def _gather_plan_du_jour(context: str = "college") -> list:
    """Pure function — agrège révisions du jour, consolidation, et lacunes actives.

    Aucune dépendance NiceGUI : réutilisable et testable indépendamment du rendu.
    """
    from backend.core.reviews.service import review_service
    from backend.core.planning.service import planning_service
    from backend.core.reviews import local_store
    from backend.core.reviews.lacune_adapter import weak_point_to_task

    history = local_store.get_all_history()
    all_tasks = review_service.generate_reviews(context=context, history=history)
    review_items = review_service.get_urgent_tasks(all_tasks) + review_service.get_today_tasks(all_tasks)

    consolidation_selected, _ = planning_service.plan_consolidation()

    weak_point_rows = local_store.get_all_weak_points_table(status_filter="active")
    lacune_items = [weak_point_to_task(row) for row in weak_point_rows]

    return review_items + consolidation_selected + lacune_items
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_todo_plan_du_jour.py -v`
Expected: PASS

- [ ] **Step 5: Render the "Plan du jour" section**

In `frontend/pages/todo.py`, add a rendering function after `_render_routine_block` (after line 164, before `_build_course_list` at line 167):

```python
def _render_plan_du_jour_block(container: ui.column) -> None:
    from frontend.pages.dashboard._dialogs import open_session_feedback_dialog
    from backend.core.reviews import local_store

    items = _gather_plan_du_jour()

    _BORDER_BY_TYPE = {"consolidation": "border-l-cyan-500", "lacune": "border-l-orange-500"}

    with container:
        with ui.element('div').classes('synapse-panel w-full p-4'):
            ui.label('PLAN DU JOUR').classes('synapse-section-label mb-2')
            if not items:
                ui.label("Rien de prévu aujourd'hui.").classes(
                    'text-sm text-slate-400 dark:text-slate-500')
                return

            def _validate(t, card, activity_types=None, duration_minutes=None,
                          confidence=None, difficulty=None, qcm_result=None,
                          weak_category=None, weak_detail=None) -> None:
                if t.review_type == "consolidation":
                    local_store.mark_consolidation_done(
                        course_id=t.course_id, context=t.context,
                        theoretical_due_date=t.theoretical_due_date,
                        course_title=t.course_title, item_number=t.item_number or "",
                        confidence=confidence or 3, difficulty=difficulty,
                    )
                elif t.review_type == "lacune":
                    weak_point_id = int(t.id.removeprefix("lacune_"))
                    local_store.resolve_weak_point(weak_point_id)
                else:
                    local_store.mark_done(
                        task_id=t.id, course_id=t.course_id, context=t.context,
                        review_type=t.review_type, theoretical_due_date=t.theoretical_due_date,
                        course_title=t.course_title, item_number=t.item_number or "",
                        difficulty=difficulty, confidence=confidence,
                    )
                local_store.add_study_session(
                    course_id=t.course_id, course_title=t.course_title,
                    item_number=t.item_number or "", context=t.context,
                    activity_types=activity_types or ["révision"],
                    duration_minutes=duration_minutes, confidence=confidence,
                    difficulty=difficulty, qcm_result=qcm_result,
                    weak_category=weak_category, weak_detail=weak_detail,
                )
                ui.notify(f"✓ Fait : {t.course_title}", type="positive")
                container.clear()
                _render_plan_du_jour_block(container)

            for t in items:
                border = _BORDER_BY_TYPE.get(t.review_type, "border-l-blue-500")
                with ui.card().classes(
                    f"w-full p-0 rounded-xl border-l-4 {border} "
                    "border-y border-r border-slate-100 dark:border-slate-800 "
                    "shadow-sm hover:shadow-md transition-all overflow-hidden mb-2"
                ) as card:
                    with ui.row().classes("items-center gap-3 px-3 py-2.5 w-full"):
                        ui.icon("task_alt", size="sm").classes("text-slate-400 shrink-0")
                        with ui.column().classes("flex-1 gap-0 min-w-0"):
                            ui.label(t.label).classes(
                                "text-sm font-semibold text-slate-800 dark:text-slate-100 leading-snug"
                            ).style("overflow:hidden;text-overflow:ellipsis;white-space:nowrap").tooltip(t.label)
                            if t.college:
                                ui.label(", ".join(t.college[:2])).classes(
                                    "text-[11px] text-slate-500 dark:text-slate-400")
                        ui.button(
                            "Valider", icon="check",
                            on_click=lambda t=t, c=card: open_session_feedback_dialog(t, c, _validate),
                        ).props("unelevated dense size=sm color=cyan")
```

- [ ] **Step 6: Wire the new section into `_render_content`**

In `frontend/pages/todo.py`, change:

```python
    with container:
        # Routine : SQLite, instantané
        routine_col = ui.column().classes('w-full')
        _render_routine_block(routine_col, date_str, cache, on_update)
```

to:

```python
    with container:
        # Plan du jour : révisions + consolidation + lacunes, instantané
        if date_obj == datetime.date.today():
            plan_col = ui.column().classes('w-full')
            _render_plan_du_jour_block(plan_col)

        # Routine : SQLite, instantané
        routine_col = ui.column().classes('w-full')
        _render_routine_block(routine_col, date_str, cache, on_update)
```

The `if date_obj == datetime.date.today()` guard matches the fact that `_gather_plan_du_jour` has no concept of a past/future day (it always answers "what's eligible right now") — showing it only on today's date avoids a confusing always-identical block on every day of the week/carousel view.

- [ ] **Step 7: Run the full test suite**

Run: `python -m pytest -q`
Expected: no new failures versus Task 4's baseline.

- [ ] **Step 8: Commit**

```bash
git add frontend/pages/todo.py tests/test_todo_plan_du_jour.py
git commit -m "feat(todo): add Plan du jour section aggregating reviews, consolidation, lacunes"
```

---

### Task 6: Manual verification

**Files:** none (verification only)

This plan's UI changes (Tasks 2-5) have no automated test for NiceGUI rendering itself — consistent with every prior Planning/Dashboard/To Do feature in this project. Verify manually against the running app:

- [ ] **Step 1: Launch the app**

Run: `python main.py` (or use the project's existing `.claude/launch.json` `synapse-consolidation-worktree`/equivalent config if working in a worktree).

- [ ] **Step 2: Dashboard — consolidation visibility**

Open the Dashboard. If at least one validated collège has a declared-level item eligible for consolidation, confirm it appears in RETARD or AUJOURD'HUI (not a separate section), with a working "Valider" button.

- [ ] **Step 3: Dashboard — consolidation validation**

Click "Valider" on a consolidation-sourced card, fill the wizard, submit. Confirm: the card disappears from the list, and `sqlite3 data/synapse_local.db "select next_interval_days from review_history where review_type='consolidation' order by completed_at desc limit 1"` shows an updated interval.

- [ ] **Step 4: Dashboard — postpone/ignore unaffected**

Postpone or ignore a normal (non-consolidation, non-lacune) review card — confirm existing behavior is unchanged (this task didn't touch the default branch's logic).

- [ ] **Step 5: Dashboard — college filter applies to consolidation**

With a consolidation-sourced card visible in RETARD/AUJOURD'HUI, click a college filter chip that does NOT match that card's college. Confirm the card disappears (filter applies to consolidation tasks the same as to regular reviews — this is what Task 3's "merge before the filter" ordering is for). Click "Tout" (or the matching chip) again and confirm it reappears.

- [ ] **Step 6: To Do — Plan du jour renders**

Open To Do on today's date. Confirm the new "PLAN DU JOUR" section appears above "ROUTINE", listing the same review/consolidation/lacune items visible on the Dashboard and Planning > Consolidation tab.

- [ ] **Step 7: To Do — lacune validation**

If there is at least one active lacune (`select * from weak_points where status='active'`), click "Valider" on its card in "Plan du jour", submit the wizard. Confirm: `select status from weak_points where id=...` now shows `résolue`, and the card disappears from the list on refresh.

- [ ] **Step 8: To Do — past/future dates unaffected**

Navigate to a different date in To Do (not today). Confirm "PLAN DU JOUR" does not appear (only on today, per Task 5 Step 6's guard) and "ROUTINE"/"AJOUTÉ" still render as before.

- [ ] **Step 9: Regression — Planning tabs unaffected**

Open Planning. Confirm Journée, Semaine, and Consolidation tabs still work exactly as before this plan (no shared code was modified in `frontend/pages/planning.py` itself — this plan only added new consumers of the same backend functions).
