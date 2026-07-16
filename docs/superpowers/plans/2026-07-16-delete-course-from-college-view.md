# Suppression d'un cours depuis une vue collège — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Supprimer" action to the CourseCard's ⋯ menu that archives the course's Notion page and removes it from the local `data_store` cache in one click, so the user can prune miscategorized/duplicate courses directly from `/colleges` without touching Notion by hand.

**Architecture:** Since the Cours DB now uses one Notion page per (item, collège) pair (see `docs/superpowers/specs/2026-07-16-delete-course-design.md`), a `Cours` object always carries exactly one entry in `course.college`. "Delete this course from this collège view" is therefore just: archive that one Notion page, then drop that one entry from `data_store.cours`. Three small, independently testable pieces: a `DataStore.remove_cours()` method, an async UI-glue helper that sequences Notion-archive → local-remove → notify/refresh, and the menu item that wires it into `CourseCard`.

**Tech Stack:** Python 3.13, NiceGUI, pytest, notion-client (async), existing `DataStore` singleton (`backend/state/store.py`) and `notion_client` singleton (`backend/core/notion/client.py`).

## Global Constraints

- No confirmation dialog — instant delete + toast, matching the existing weak-point "Supprimer" pattern (`frontend/components/weak_point_card.py:284`).
- Only the single Notion page for this (item, collège) pair is touched — never other pages for the same item in other collèges.
- Local cache is only mutated **after** the Notion archive call succeeds — never leave Notion and the local cache in different states.
- Follow the existing async-action pattern already used in this file: `async def` helper, invoked via `asyncio.create_task(...)`, using `with ctx:` (the `client` param, falling back to `ui.context.client`) to touch the UI after the `await` — see `_create_obsidian_note_action` in `frontend/components/course_quick_actions.py:410-422`.

---

### Task 1: `DataStore.remove_cours()`

**Files:**
- Modify: `backend/state/store.py:503-515` (insert new method right after `merge_cours_delta`, before the `# ... getters ...` comment on line 517)
- Test: `tests/test_store_remove_cours.py` (new file)

**Interfaces:**
- Produces: `async def DataStore.remove_cours(self, course_id: str) -> None` — removes the `Cours` with matching `.id` from `self.cours` (no-op if not found), persists via `self.save_to_disk()`. Instance method on the `DataStore` class (not static, unlike `_deduplicate_cours`), since it mutates `self.cours` and calls `self.save_to_disk()`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_store_remove_cours.py`. This project does **not** have `pytest-asyncio` installed — the established convention for testing `async def` code (see `tests/test_files.py:27-29`) is a local `_run(coro)` helper wrapping `asyncio.get_event_loop().run_until_complete(coro)`, with plain `def test_...` functions (not `async def`, no `@pytest.mark.asyncio`). Follow that exact pattern:

```python
"""Tests pour DataStore.remove_cours()"""
import asyncio
from datetime import datetime
from unittest.mock import patch
from backend.state.store import DataStore
from backend.core.notion.models import Cours


def _make_cours(id_: str, title: str, item_number: str = "", college: list = None) -> Cours:
    return Cours(
        id=id_,
        title=title,
        item_number=item_number,
        college=college or [],
        created_time=datetime(2024, 1, 1),
    )


def _run(coro):
    """Exécute une coroutine de manière synchrone pour les tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestRemoveCours:
    def test_removes_matching_course(self):
        store = DataStore()
        store.cours = [
            _make_cours("a", "Splénomégalie", "275", college=["Médecine interne"]),
            _make_cours("b", "Splénomégalie", "275", college=["Hématologie"]),
        ]
        with patch.object(DataStore, "save_to_disk"):
            _run(store.remove_cours("a"))
        ids = {c.id for c in store.cours}
        assert ids == {"b"}

    def test_noop_when_id_not_found(self):
        store = DataStore()
        store.cours = [_make_cours("a", "Dyslipidémies", "223")]
        with patch.object(DataStore, "save_to_disk"):
            _run(store.remove_cours("does-not-exist"))
        ids = {c.id for c in store.cours}
        assert ids == {"a"}

    def test_persists_to_disk(self):
        store = DataStore()
        store.cours = [_make_cours("a", "Dyslipidémies", "223")]
        with patch.object(DataStore, "save_to_disk") as mock_save:
            _run(store.remove_cours("a"))
        mock_save.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_store_remove_cours.py -v`
Expected: FAIL — `AttributeError: 'DataStore' object has no attribute 'remove_cours'`

- [ ] **Step 3: Write minimal implementation**

In `backend/state/store.py`, insert this method immediately after `merge_cours_delta` (which currently ends at line 515, right before the `# ... getters ...` comment on line 517):

```python
    async def remove_cours(self, course_id: str) -> None:
        """Retire un Cours du store local (après suppression Notion) et persiste."""
        async with self._cours_lock:
            self.cours = [c for c in self.cours if c.id != course_id]
        self.save_to_disk()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_store_remove_cours.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/state/store.py tests/test_store_remove_cours.py
git commit -m "feat(store): add DataStore.remove_cours() for single-course deletion"
```

---

### Task 2: `_delete_course_action()` UI-glue helper

**Files:**
- Modify: `frontend/components/course_quick_actions.py` (add near `_create_obsidian_note_action`, ~line 408-422; add `from backend.core.notion.client import notion_client` and `from backend.state.store import data_store` to the existing import block at the top of the file, lines 19-32)
- Test: `tests/test_delete_course_action.py` (new file)

**Interfaces:**
- Consumes: `DataStore.remove_cours(course_id: str) -> None` (async, from Task 1); `notion_client.archive_page(page_id: str)` (async, existing — `backend/core/notion/client.py:95-101`, singleton importable as `from backend.core.notion.client import notion_client`).
- Produces: `async def _delete_course_action(course, refresh_fn, client) -> None` — same call signature shape as `_create_obsidian_note_action(course, refresh_fn, client)` at line 410, so `CourseCard` (Task 3) can wire it identically.

- [ ] **Step 1: Write the failing test**

Create `tests/test_delete_course_action.py`. Same no-`pytest-asyncio` convention as Task 1 (local `_run(coro)` helper, plain `def test_...`). No existing test in this repo touches `ui.context.client` or `ui.notify`, so avoid depending on NiceGUI's request-context internals: always pass an explicit `client` (a `MagicMock()`, which supports the `with ctx:` context-manager protocol out of the box) so the `ui.context.client` fallback branch in `_delete_course_action` is never exercised by the test.

```python
"""Tests pour _delete_course_action()"""
import asyncio
from types import SimpleNamespace
from unittest.mock import patch, Mock, MagicMock, AsyncMock
from frontend.components.course_quick_actions import _delete_course_action


def _make_course(id_="c1", college=None):
    return SimpleNamespace(id=id_, title="Splénomégalie", college=college or ["Hématologie"])


def _run(coro):
    """Exécute une coroutine de manière synchrone pour les tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestDeleteCourseAction:
    def test_archives_notion_then_removes_locally_on_success(self):
        course = _make_course()
        refresh_fn = Mock()
        fake_client = MagicMock()
        with patch(
            "frontend.components.course_quick_actions.notion_client.archive_page",
            new_callable=AsyncMock,
        ) as mock_archive, patch(
            "frontend.components.course_quick_actions.data_store.remove_cours",
            new_callable=AsyncMock,
        ) as mock_remove, patch(
            "frontend.components.course_quick_actions.ui.notify"
        ) as mock_notify:
            _run(_delete_course_action(course, refresh_fn, client=fake_client))

        mock_archive.assert_awaited_once_with("c1")
        mock_remove.assert_awaited_once_with("c1")
        refresh_fn.assert_called_once()
        assert mock_notify.call_args.kwargs.get("type") == "warning"

    def test_does_not_touch_local_store_if_notion_archive_fails(self):
        course = _make_course()
        refresh_fn = Mock()
        fake_client = MagicMock()
        with patch(
            "frontend.components.course_quick_actions.notion_client.archive_page",
            new_callable=AsyncMock,
            side_effect=Exception("Notion API error"),
        ), patch(
            "frontend.components.course_quick_actions.data_store.remove_cours",
            new_callable=AsyncMock,
        ) as mock_remove, patch(
            "frontend.components.course_quick_actions.ui.notify"
        ) as mock_notify:
            _run(_delete_course_action(course, refresh_fn, client=fake_client))

        mock_remove.assert_not_called()
        refresh_fn.assert_not_called()
        assert mock_notify.call_args.kwargs.get("type") == "negative"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_delete_course_action.py -v`
Expected: FAIL — `ImportError: cannot import name '_delete_course_action'`

- [ ] **Step 3: Write minimal implementation**

Add to the import block at the top of `frontend/components/course_quick_actions.py` (alongside the existing imports at lines 19-27):

```python
from backend.core.notion.client import notion_client
from backend.state.store import data_store
```

Add the function near `_create_obsidian_note_action` (after line 422, before `def _open_obsidian_note_action`):

```python
async def _delete_course_action(course, refresh_fn, client) -> None:
    """Archive la page Notion du cours puis le retire du cache local (une page = un couple (item, collège))."""
    try:
        await notion_client.archive_page(course.id)
    except Exception as exc:
        try:
            ctx = client if client else ui.context.client
            with ctx:
                ui.notify(f"Erreur suppression : {exc}", type="negative")
        except Exception:
            pass
        return

    await data_store.remove_cours(course.id)

    try:
        ctx = client if client else ui.context.client
        with ctx:
            ui.notify(f"« {course.title} » supprimé de {', '.join(course.college)} ✓", type="warning", icon="delete")
            if refresh_fn:
                refresh_fn()
    except Exception:
        pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_delete_course_action.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add frontend/components/course_quick_actions.py tests/test_delete_course_action.py
git commit -m "feat(course-actions): add _delete_course_action Notion+cache deletion helper"
```

---

### Task 3: Wire "Supprimer" into the CourseCard menu

**Files:**
- Modify: `frontend/components/course_card.py:22-31` (import block) and `frontend/components/course_card.py:244-245` (insert new menu section)

**Interfaces:**
- Consumes: `_delete_course_action(course, refresh_fn, client)` (async, from Task 2).

- [ ] **Step 1: Add the import**

In `frontend/components/course_card.py`, extend the existing import from `frontend.components.course_quick_actions` (lines 22-31):

```python
from frontend.components.course_quick_actions import (
    quick_mark_course_action,
    open_quick_session_dialog,
    open_start_tracking_dialog,
    _open_quick_qcm_dialog,
    _open_obsidian_note_action,
    _create_obsidian_note_action,
    _open_link_note_dialog,
    open_pdf_wizard,
    _delete_course_action,
)
```

- [ ] **Step 2: Add the menu item**

In `frontend/components/course_card.py`, insert immediately after line 244 (the closing `)` of the last `ui.label(lbl)` in the "Complétion" section) and before line 246 (`# Ligne 2 : dot maîtrise...`), at the same 24-space indent as the surrounding section markers:

```python

                        ui.separator().classes("my-1")

                        # ── 5. Suppression ────────────────────────────────────
                        ui.menu_item(
                            "Supprimer",
                            on_click=lambda c=course: asyncio.create_task(
                                _delete_course_action(c, refresh_fn, client)
                            ),
                        ).props("dense").classes("text-[13px] text-red-500")
```

(`asyncio` is already imported at the top of `course_card.py` line 19, used by the existing "Créer note Obsidian" menu item at line 202.)

- [ ] **Step 3: Manual verification**

This task has no automated test (it's declarative NiceGUI wiring already covered by Task 1/2 unit tests) — verify by running the app:

1. Launch the app (see project's normal run command / the `run` skill if unsure).
2. Go to `/colleges`, open a collège with a course you know is miscategorized (or any test course you're OK removing).
3. Click the ⋯ menu on its `CourseCard`, click "Supprimer" (red, bottom of menu).
4. Confirm: a warning toast appears, the card disappears from the view immediately (no page reload needed).
5. Reload the page: the card must not reappear (confirms it was actually removed from the local cache, not just from the in-memory render).
6. Run `python scripts/diff_college_mapping.py` — the deleted item/collège pair should now show up under `items_missing_from_notion` (or simply be absent from `current`), confirming the Notion page was actually archived, not just hidden locally.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/course_card.py
git commit -m "feat(course-card): wire Supprimer menu item to delete course from college view"
```

## Self-Review Notes

- **Spec coverage:** menu location + red styling (spec ✓ Task 3), instant delete no dialog (spec ✓ Task 2), Notion archive before local removal with rollback-free failure handling (spec ✓ Task 2 step 3), `DataStore.remove_cours` symmetric with `refresh`/`merge_cours_delta` (spec ✓ Task 1), derived-cache staleness explicitly out of scope (spec — no task needed, nothing to build).
- **Type consistency:** `_delete_course_action(course, refresh_fn, client)` signature matches `_create_obsidian_note_action(course, refresh_fn, client)` exactly (Task 2 produces, Task 3 consumes). `DataStore.remove_cours(course_id: str)` signature matches between Task 1 (produces) and Task 2 (consumes).
- **No placeholders:** all steps contain complete, runnable code.
