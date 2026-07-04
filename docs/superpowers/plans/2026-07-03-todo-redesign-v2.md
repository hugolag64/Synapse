# To Do — refonte v2 (hero, strip semaine, panels, utile+++) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `frontend/pages/todo.py` with a hero banner (progress ring, streak, "reporté d'hier" signal), a clickable 7-day strip, panel-based section blocks, an empty-state CTA, a repositioned quick-add, and an undo action on course validation — while staying visually consistent with the hero/KPI/panel language already shipped on `/qcm` and `/stats`.

**Architecture:** A new `_DaySummary` dataclass + a page-local cache (`dict[str, _DaySummary]`) become the single source of truth for progress numbers, replacing the ad-hoc `progress_state` dict. Pure aggregation logic (`_compute_ajoute_progress`, `_compute_carryover`, `_week_dates`, `_DaySummary.pct`) is extracted into unit-tested functions; async orchestration (`_get_day_summary`, `_get_yesterday_carryover`) stays thin and is verified manually in the browser, matching this codebase's existing convention of only unit-testing pure logic (see `tests/test_todo_logic.py`, no async tests exist anywhere in this repo today).

**Tech Stack:** NiceGUI (Python), Notion API via `backend/core/notion/service.py`, SQLite via `backend/core/reviews/local_store.py`, `static/synapse.css` design tokens.

## Global Constraints

- No new Notion property/field, no SQLite migration — spec `docs/superpowers/specs/2026-07-03-todo-redesign-v2-design.md` section 9 caps backend additions at exactly 2 new service functions.
- No automatic carry-over / move of Notion data between days — carry-over is a read-only badge only (spec, "Contexte" section).
- The week-strip's 7 Notion enrichment calls run sequentially, never via `asyncio.gather` (spec section 3 — deliberate throttle).
- Undo only applies to course validation in the Ajouté block, not to Routine (spec section 8 / "Contexte").
- Reuse `static/synapse.css` tokens/classes as-is (`.synapse-hero`, `.synapse-ring`, `.synapse-panel`, `.synapse-section-label`) — no new color palette.
- Only pure functions get `pytest` unit tests, following `tests/test_todo_logic.py`'s existing convention; async orchestration is verified by running the app locally (no pytest-asyncio in this project).

---

## Task 1: Extract and test `_compute_ajoute_progress`

**Files:**
- Modify: `frontend/pages/todo.py:171-176` (inside `_render_ajout_block`)
- Test: `tests/test_todo_logic.py`

**Interfaces:**
- Produces: `_compute_ajoute_progress(course_items: list[dict], reviewed_titles: list[str], dynamic_tasks: dict) -> tuple[int, int]` — returns `(total, done)`. Used by later tasks (2, 5, 6).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_todo_logic.py` (reuses the existing `courses` fixture and `_MockCourse`):

```python
from frontend.pages.todo import _build_course_list, _compute_ajoute_progress


class TestComputeAjouteProgress:
    def test_empty(self):
        assert _compute_ajoute_progress([], [], {}) == (0, 0)

    def test_all_courses_reviewed(self, courses):
        items = [{'course': courses[0]}, {'course': courses[1]}]
        reviewed = [courses[0].title, courses[1].title]
        assert _compute_ajoute_progress(items, reviewed, {}) == (2, 2)

    def test_partial_courses(self, courses):
        items = [{'course': courses[0]}, {'course': courses[1]}]
        reviewed = [courses[0].title]
        assert _compute_ajoute_progress(items, reviewed, {}) == (2, 1)

    def test_dynamic_tasks_only(self):
        dynamic = {'b1': {'text': 'x', 'checked': True}, 'b2': {'text': 'y', 'checked': False}}
        assert _compute_ajoute_progress([], [], dynamic) == (2, 1)

    def test_mixed_courses_and_dynamic(self, courses):
        items = [{'course': courses[0]}]
        reviewed = [courses[0].title]
        dynamic = {'b1': {'text': 'x', 'checked': False}}
        assert _compute_ajoute_progress(items, reviewed, dynamic) == (2, 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_todo_logic.py::TestComputeAjouteProgress -v`
Expected: FAIL with `ImportError: cannot import name '_compute_ajoute_progress'`

- [ ] **Step 3: Add the function and refactor the call site**

In `frontend/pages/todo.py`, add near the top (after `_safe_item_number`, before `_render_content`):

```python
def _compute_ajoute_progress(
    course_items: list[dict],
    reviewed_titles: list[str],
    dynamic_tasks: dict,
) -> tuple[int, int]:
    """Retourne (total, done) pour le bloc Ajouté : cours + tâches libres."""
    total = len(course_items) + len(dynamic_tasks)
    done = (
        sum(1 for r in course_items if r['course'].title in reviewed_titles)
        + sum(1 for d in dynamic_tasks.values() if d['checked'])
    )
    return total, done
```

Replace lines 171-176 of `_render_ajout_block` (currently):

```python
    dynamic_tasks = task.dynamic_checkboxes if task else {}
    ajout_total = len(course_items) + len(dynamic_tasks)
    ajout_done  = (sum(1 for r in course_items if r['course'].title in reviewed_titles)
                   + sum(1 for d in dynamic_tasks.values() if d['checked']))
    # Écrase (ne cumule pas) pour éviter le double-comptage lors des re-renders
    progress_state['ajout'] = [ajout_total, ajout_done]
```

with:

```python
    dynamic_tasks = task.dynamic_checkboxes if task else {}
    ajout_total, ajout_done = _compute_ajoute_progress(course_items, reviewed_titles, dynamic_tasks)
    # Écrase (ne cumule pas) pour éviter le double-comptage lors des re-renders
    progress_state['ajout'] = [ajout_total, ajout_done]
```

(This step keeps `progress_state` for now — it is fully replaced by the cache in Task 5. Keeping this task additive-only makes it independently reviewable.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_todo_logic.py -v`
Expected: all tests PASS (13 total: 8 existing + 5 new)

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/todo.py tests/test_todo_logic.py
git commit -m "refactor: extract _compute_ajoute_progress as a pure, tested function"
```

---

## Task 2: Add `_DaySummary` dataclass

**Files:**
- Modify: `frontend/pages/todo.py` (top of file, after imports)
- Test: `tests/test_todo_logic.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `_DaySummary` dataclass with fields `routine_total: int = 0`, `routine_done: int = 0`, `ajoute_total: int = 0`, `ajoute_done: int = 0`, `ajoute_loaded: bool = False`, and properties `.total`, `.done`, `.pct`. Used by Tasks 3, 5, 6, 8, 9, 10, 11.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_todo_logic.py`:

```python
from frontend.pages.todo import _DaySummary


class TestDaySummary:
    def test_pct_zero_total(self):
        assert _DaySummary().pct == 0.0

    def test_pct_routine_only(self):
        s = _DaySummary(routine_total=4, routine_done=2)
        assert s.pct == 0.5

    def test_pct_full(self):
        s = _DaySummary(routine_total=2, routine_done=2, ajoute_total=2, ajoute_done=2, ajoute_loaded=True)
        assert s.pct == 1.0

    def test_pct_partial_with_ajoute(self):
        s = _DaySummary(routine_total=4, routine_done=4, ajoute_total=4, ajoute_done=1, ajoute_loaded=True)
        assert s.pct == pytest.approx(0.625)

    def test_total_and_done(self):
        s = _DaySummary(routine_total=3, routine_done=1, ajoute_total=2, ajoute_done=2)
        assert s.total == 5
        assert s.done == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_todo_logic.py::TestDaySummary -v`
Expected: FAIL with `ImportError: cannot import name '_DaySummary'`

- [ ] **Step 3: Add the dataclass**

In `frontend/pages/todo.py`, add `from dataclasses import dataclass` to the imports at the top of the file:

```python
from nicegui import ui
from backend.core.notion.service import notion_service
from backend.core.google.calendar_service import calendar_service
from backend.core.reviews import local_store
from backend.state.store import data_store
from frontend.theme import frame
from dataclasses import dataclass
import asyncio
import datetime
```

Then add, right after the `_DAYS` constant:

```python
@dataclass
class _DaySummary:
    routine_total: int = 0
    routine_done: int = 0
    ajoute_total: int = 0
    ajoute_done: int = 0
    ajoute_loaded: bool = False

    @property
    def total(self) -> int:
        return self.routine_total + self.ajoute_total

    @property
    def done(self) -> int:
        return self.routine_done + self.ajoute_done

    @property
    def pct(self) -> float:
        return (self.done / self.total) if self.total > 0 else 0.0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_todo_logic.py -v`
Expected: all 18 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/todo.py tests/test_todo_logic.py
git commit -m "feat: add _DaySummary dataclass for unified day progress tracking"
```

---

## Task 3: Extract and test `_compute_carryover` and `_week_dates`

**Files:**
- Modify: `frontend/pages/todo.py`
- Test: `tests/test_todo_logic.py`

**Interfaces:**
- Produces: `_compute_carryover(manual_titles: list[str], reviewed_titles: list[str]) -> list[str]` and `_week_dates(center: datetime.date) -> list[datetime.date]`. Used by Tasks 6 (carryover) and 9/11 (week strip).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_todo_logic.py`:

```python
import datetime
from frontend.pages.todo import _compute_carryover, _week_dates


class TestComputeCarryover:
    def test_empty(self):
        assert _compute_carryover([], []) == []

    def test_all_done(self):
        assert _compute_carryover(['A', 'B'], ['A', 'B']) == []

    def test_none_done(self):
        assert _compute_carryover(['A', 'B'], []) == ['A', 'B']

    def test_partial(self):
        assert _compute_carryover(['A', 'B', 'C'], ['B']) == ['A', 'C']


class TestWeekDates:
    def test_length(self):
        assert len(_week_dates(datetime.date(2026, 7, 3))) == 7

    def test_centered(self):
        result = _week_dates(datetime.date(2026, 7, 3))
        assert result[3] == datetime.date(2026, 7, 3)
        assert result[0] == datetime.date(2026, 6, 30)
        assert result[6] == datetime.date(2026, 7, 6)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_todo_logic.py::TestComputeCarryover tests/test_todo_logic.py::TestWeekDates -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Add the functions**

In `frontend/pages/todo.py`, add near `_compute_ajoute_progress`:

```python
def _compute_carryover(manual_titles: list[str], reviewed_titles: list[str]) -> list[str]:
    """Titres de cours manuels programmés qui ne sont pas (encore) marqués révisés."""
    return [t for t in manual_titles if t not in reviewed_titles]


def _week_dates(center: datetime.date) -> list[datetime.date]:
    """Fenêtre de 7 jours centrée sur `center` (J-3 à J+3)."""
    return [center + datetime.timedelta(days=offset) for offset in range(-3, 4)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_todo_logic.py -v`
Expected: all 24 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/todo.py tests/test_todo_logic.py
git commit -m "feat: add _compute_carryover and _week_dates pure helpers"
```

---

## Task 4: Backend — add `unmark_manual_revision_done` and `remove_course_from_daily_reviewed`

**Files:**
- Modify: `backend/core/notion/service.py` (after `mark_manual_revision_done`, ~line 673)

**Interfaces:**
- Consumes: `notion_client.retrieve_block_children`, `notion_client.update_block` (both already exist in `backend/core/notion/client.py`).
- Produces: `notion_service.unmark_manual_revision_done(page_id: str, course_title: str) -> bool` and `notion_service.remove_course_from_daily_reviewed(page_id: str, course_title: str) -> bool`. Used by Task 8 (undo).

No unit test for this task: it is pure Notion API orchestration with no pytest-asyncio infrastructure in this project (consistent with `mark_manual_revision_done` above it, which also has no dedicated test). Verified manually in Task 14.

- [ ] **Step 1: Add `unmark_manual_revision_done`**

In `backend/core/notion/service.py`, insert immediately after the `mark_manual_revision_done` method (after line 673, before `find_course_by_title`):

```python
    async def unmark_manual_revision_done(self, page_id: str, course_title: str) -> bool:
        """Undo mark_manual_revision_done: revert a 'Révisé' block back to 'Manuel' (unchecked)."""
        try:
            response = await notion_client.retrieve_block_children(page_id)
            blocks = response.get("results", [])

            target_block_id = None
            for block in blocks:
                if block.get("type") == "to_do":
                    todo = block["to_do"]
                    rich_text = todo.get("rich_text", [])
                    if rich_text:
                        content = rich_text[0].get("text", {}).get("content", "")
                        if todo.get("checked") and content == f"Révisé : {course_title}":
                            target_block_id = block["id"]
                            break

            if target_block_id:
                await notion_client.update_block(
                    block_id=target_block_id,
                    to_do={
                        "checked": False,
                        "rich_text": [{"text": {"content": f"Manuel : {course_title}"}}],
                    },
                )
                logger.success(f"Reverted manual revision '{course_title}' to pending.")
                return True
            else:
                logger.warning(f"Could not find reviewed block for '{course_title}' to undo")
                return False

        except Exception as e:
            logger.error(f"Failed to unmark manual revision: {e}")
            return False

    async def remove_course_from_daily_reviewed(self, page_id: str, course_title: str) -> bool:
        """Undo add_course_to_daily_reviewed: archive the 'Révisé' block (no manual counterpart to revert to)."""
        try:
            response = await notion_client.retrieve_block_children(page_id)
            blocks = response.get("results", [])

            target_block_id = None
            for block in blocks:
                if block.get("type") == "to_do":
                    todo = block["to_do"]
                    rich_text = todo.get("rich_text", [])
                    if rich_text:
                        content = rich_text[0].get("text", {}).get("content", "")
                        if content == f"Révisé : {course_title}":
                            target_block_id = block["id"]
                            break

            if target_block_id:
                await notion_client.update_block(block_id=target_block_id, archived=True)
                logger.success(f"Removed reviewed block for '{course_title}'.")
                return True
            else:
                logger.warning(f"Could not find reviewed block for '{course_title}' to remove")
                return False

        except Exception as e:
            logger.error(f"Failed to remove course from daily reviewed: {e}")
            return False
```

- [ ] **Step 2: Sanity-check the module still imports**

Run: `python -c "from backend.core.notion.service import notion_service; print(hasattr(notion_service, 'unmark_manual_revision_done'), hasattr(notion_service, 'remove_course_from_daily_reviewed'))"`
Expected: `True True`

- [ ] **Step 3: Commit**

```bash
git add backend/core/notion/service.py
git commit -m "feat: add unmark_manual_revision_done and remove_course_from_daily_reviewed for undo support"
```

---

## Task 5: Replace `progress_state` with the `_DaySummary` cache in the render pipeline

**Files:**
- Modify: `frontend/pages/todo.py:27-159` (`_render_content`, `_render_routine_block`, `_load_and_render_network_blocs`, `_render_ajout_block`)

**Interfaces:**
- Consumes: `_DaySummary` (Task 2), `_compute_ajoute_progress` (Task 1).
- Produces: `_get_routine_summary(date_obj) -> _DaySummary`, `_refresh_routine_in_cache(date_obj, cache) -> _DaySummary`. `_render_content`, `_render_routine_block`, `_load_and_render_network_blocs`, `_render_ajout_block` now take `cache: dict[str, _DaySummary]` and `on_update: Callable[[], None]` instead of `progress_state: dict` and `refresh_progress`. Used by Task 14 (final assembly) and Task 8 (undo, reads `cache[date_str]`).

No dedicated unit test: this task rewires I/O-bound rendering functions (calls `local_store`, builds NiceGUI elements) with no behavior change to verify beyond what Task 1/2/3's tests already cover for the underlying pure logic. Verified manually in Task 14 (the page must still track progress correctly end-to-end).

- [ ] **Step 1: Add `_get_routine_summary` and `_refresh_routine_in_cache`**

In `frontend/pages/todo.py`, add near `_render_routine_block`:

```python
def _get_routine_summary(date_obj: datetime.date) -> _DaySummary:
    date_str = date_obj.isoformat()
    items = local_store.get_routine_items()
    checks = local_store.get_routine_checks(date_str)
    return _DaySummary(
        routine_total=len(items),
        routine_done=sum(1 for name in items if checks.get(name, False)),
    )


def _refresh_routine_in_cache(date_obj: datetime.date, cache: dict) -> "_DaySummary":
    """(Re)calcule la partie routine et la fusionne dans le cache, en conservant
    Ajouté si déjà chargé (évite d'écraser un résumé déjà enrichi par la strip)."""
    date_str = date_obj.isoformat()
    routine = _get_routine_summary(date_obj)
    existing = cache.get(date_str)
    if existing and existing.ajoute_loaded:
        existing.routine_total = routine.routine_total
        existing.routine_done = routine.routine_done
        cache[date_str] = existing
        return existing
    cache[date_str] = routine
    return routine
```

- [ ] **Step 2: Rewrite `_render_content`**

Replace the full `_render_content` function (lines 27-53) with:

```python
async def _render_content(
    container: ui.column,
    date_obj: datetime.date,
    cache: dict,
    on_update,
) -> None:
    container.clear()
    if container.is_deleted:
        return
    date_str = date_obj.isoformat()
    is_past  = date_obj < datetime.date.today()

    _refresh_routine_in_cache(date_obj, cache)

    with container:
        # Routine : SQLite, instantané
        routine_col = ui.column().classes('w-full')
        _render_routine_block(routine_col, date_str, cache, on_update)

        # Ajouté + Note : chargés en réseau (tâches 4 et 5)
        ajout_col = ui.column().classes('w-full')
        note_col  = ui.column().classes('w-full')

        asyncio.create_task(
            _load_and_render_network_blocs(
                ajout_col, note_col, date_obj, is_past, cache, on_update,
            )
        )
```

- [ ] **Step 3: Rewrite `_render_routine_block`**

Replace the full `_render_routine_block` function (lines 56-91) with:

```python
def _render_routine_block(
    container: ui.column,
    date_str: str,
    cache: dict,
    on_update,
) -> None:
    items  = local_store.get_routine_items()
    checks = local_store.get_routine_checks(date_str)
    summary = cache[date_str]

    with container:
        with ui.row().classes('w-full gap-4 items-start'):
            ui.element('div').classes('w-1 rounded-full bg-sky-500 self-stretch min-h-[2rem]')
            with ui.column().classes('flex-1 gap-2'):
                ui.label('ROUTINE').classes(
                    'text-xs font-bold uppercase tracking-widest text-slate-400 mb-1')
                with ui.element('div').classes(
                        'grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-2'):
                    for name in items:
                        checked = checks.get(name, False)

                        def _on_toggle(e, item_name=name):
                            delta = 1 if e.value else -1
                            summary.routine_done = max(
                                0, min(summary.routine_total, summary.routine_done + delta))
                            on_update()
                            local_store.set_routine_check(date_str, item_name, e.value)

                        ui.checkbox(name, value=checked, on_change=_on_toggle).props('dense').classes(
                            'text-slate-700 dark:text-slate-200 transition-opacity duration-200')

    on_update()
```

(Visual styling — the colored bar and Tailwind label classes — is intentionally unchanged here; Task 12 handles the `.synapse-panel` conversion as its own reviewable diff.)

- [ ] **Step 4: Rewrite `_load_and_render_network_blocs`**

Replace the full function (lines 125-159) with:

```python
async def _load_and_render_network_blocs(
    ajout_col: ui.column,
    note_col: ui.column,
    date_obj: datetime.date,
    is_past: bool,
    cache: dict,
    on_update,
) -> None:
    _render_skeleton_bloc(ajout_col, 'bg-violet-500', 'AJOUTÉ')
    _render_skeleton_bloc(note_col,  'bg-amber-500',  'NOTE DU JOUR')

    task, events = await asyncio.gather(
        notion_service.get_daily_task_by_date(date_obj),
        calendar_service.get_events_for_day(date_obj),
    )

    reviewed_titles: list[str] = []
    manual_titles:   list[str] = []
    if task:
        reviewed_titles, manual_titles = await asyncio.gather(
            notion_service.get_daily_reviewed_courses(task.id),
            notion_service.get_daily_manual_revision_courses(task.id),
        )

    if ajout_col.is_deleted or note_col.is_deleted:
        return

    course_items = _build_course_list(events, manual_titles, data_store.cours)

    await _render_ajout_block(
        ajout_col, date_obj, task, course_items,
        reviewed_titles, cache, on_update,
    )
    _render_note_block(note_col, task, is_past)
    on_update()
```

- [ ] **Step 5: Rewrite `_render_ajout_block` and `_render_course_item` call sites**

Replace lines 162-240 (`_render_ajout_block`) with:

```python
async def _render_ajout_block(
    container: ui.column,
    date_obj: datetime.date,
    task,
    course_items: list[dict],
    reviewed_titles: list[str],
    cache: dict,
    on_update,
) -> None:
    date_str = date_obj.isoformat()
    dynamic_tasks = task.dynamic_checkboxes if task else {}
    ajoute_total, ajoute_done = _compute_ajoute_progress(course_items, reviewed_titles, dynamic_tasks)

    summary = cache[date_str]
    summary.ajoute_total = ajoute_total
    summary.ajoute_done = ajoute_done
    summary.ajoute_loaded = True

    container.clear()
    with container:
        with ui.row().classes('w-full gap-4 items-start'):
            ui.element('div').classes('w-1 rounded-full bg-violet-500 self-stretch min-h-[2rem]')
            with ui.column().classes('flex-1 gap-2'):
                ui.label('AJOUTÉ').classes(
                    'text-xs font-bold uppercase tracking-widest text-slate-400 mb-1')

                # ── Cours ─────────────────────────────────────────────────────
                for item in course_items:
                    _render_course_item(
                        item['course'], item['course'].title in reviewed_titles,
                        item['type'], task, cache, date_str, on_update,
                    )

                # ── Tâches dynamiques ─────────────────────────────────────────
                for b_id, data in dynamic_tasks.items():
                    async def _toggle_dyn(e, bid=b_id):
                        delta = 1 if e.value else -1
                        summary.ajoute_done = max(
                            0, min(summary.ajoute_total, summary.ajoute_done + delta))
                        on_update()
                        await notion_service.toggle_dynamic_task(bid, e.value)

                    ui.checkbox(data['text'], value=data['checked'],
                                on_change=_toggle_dyn).props('dense').classes(
                        'text-slate-700 dark:text-slate-200')

                if not course_items and not dynamic_tasks:
                    ui.label('Rien de planifié pour ce jour.').classes(
                        'text-sm text-slate-400 italic')

                # ── Contrôles d'ajout ─────────────────────────────────────────
                with ui.row().classes(
                        'items-center gap-2 mt-2 pt-2 '
                        'border-t border-slate-100 dark:border-slate-800'):
                    ui.button('+ Cours',
                              on_click=lambda: _open_add_course_dialog(date_obj, task)).props(
                        'flat dense').classes(
                        'text-violet-600 dark:text-violet-400 text-sm font-medium')

                    new_task_input = ui.input(placeholder='+ Tâche libre…').props(
                        'borderless dense').classes('flex-1 text-sm text-slate-600 dark:text-slate-300')

                    async def _add_task_free():
                        val = new_task_input.value.strip()
                        if not val or not task:
                            return
                        new_task_input.value = ''
                        if await notion_service.add_dynamic_task(task.id, val):
                            ui.notify('Tâche ajoutée', type='positive')
                            updated = await notion_service.get_daily_task_by_date(date_obj)
                            if updated and not container.is_deleted:
                                await _render_ajout_block(
                                    container, date_obj, updated, course_items,
                                    reviewed_titles, cache, on_update,
                                )

                    new_task_input.on('keydown.enter',
                                      lambda: asyncio.create_task(_add_task_free()))
                    ui.button(icon='send',
                              on_click=lambda: asyncio.create_task(_add_task_free())).props(
                        'flat round dense').classes('text-violet-500')
```

- [ ] **Step 6: Verify the module still imports and existing tests pass**

Run: `python -m pytest tests/test_todo_logic.py -v`
Expected: all 24 tests PASS (no test touches these rendering functions, this confirms no import-time breakage)

Run: `python -c "import frontend.pages.todo"`
Expected: no error

- [ ] **Step 7: Commit**

```bash
git add frontend/pages/todo.py
git commit -m "refactor: replace progress_state dict with shared _DaySummary cache"
```

---

## Task 6: Undo support on course validation

**Files:**
- Modify: `frontend/pages/todo.py:243-285` (`_render_course_item`)

**Interfaces:**
- Consumes: `notion_service.unmark_manual_revision_done`, `notion_service.remove_course_from_daily_reviewed` (Task 4), `_DaySummary` cache (Task 5).
- Produces: updated `_render_course_item(c, is_reviewed, source_type, task, cache, date_str, on_update)` signature (was `progress_state, refresh_progress`). Used by Task 5's `_render_ajout_block` call site (already updated in Task 5 step 5).

No dedicated unit test: this wires `ui.notify` actions and Notion undo calls, verified manually in Task 14 (validate a course, click "Annuler", confirm it reverts).

- [ ] **Step 1: Rewrite `_render_course_item`**

Replace the full function (lines 243-285) with:

```python
def _render_course_item(
    c,
    is_reviewed: bool,
    source_type: str,
    task,
    cache: dict,
    date_str: str,
    on_update,
) -> None:
    bg = ('bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
          if is_reviewed else
          'bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-700')

    with ui.row().classes(
            f'w-full items-center justify-between p-3 rounded-xl {bg} '
            f'transition-all duration-300'):
        with ui.column().classes('gap-0.5 flex-1 min-w-0'):
            title_cls = ('text-sm font-medium text-slate-400 line-through'
                         if is_reviewed else
                         'text-sm font-medium text-slate-700 dark:text-slate-200 truncate')
            ui.label(c.title).classes(title_cls)
            badge_color = 'text-blue-400' if source_type == 'gcal' else 'text-violet-400'
            badge_text  = 'GCal' if source_type == 'gcal' else 'Manuel'
            ui.label(badge_text).classes(f'text-xs {badge_color}')

        if is_reviewed:
            ui.icon('check_circle', color='green', size='sm')
        else:
            async def _validate(course=c, s=source_type):
                ui.notify(f'Validation de {course.title}…', type='ongoing')
                await notion_service.increment_lecture_college(course.id, course.nb_lectures)
                if task:
                    if s == 'notion_manual':
                        await notion_service.mark_manual_revision_done(task.id, course.title)
                    else:
                        await notion_service.add_course_to_daily_reviewed(task.id, course.title)
                course.nb_lectures += 1
                summary = cache[date_str]
                summary.ajoute_done = min(summary.ajoute_total, summary.ajoute_done + 1)
                on_update()

                async def _undo():
                    course.nb_lectures = max(0, course.nb_lectures - 1)
                    if task:
                        if s == 'notion_manual':
                            await notion_service.unmark_manual_revision_done(task.id, course.title)
                        else:
                            await notion_service.remove_course_from_daily_reviewed(task.id, course.title)
                    summary.ajoute_done = max(0, summary.ajoute_done - 1)
                    on_update()
                    ui.notify('Validation annulée', type='info')

                ui.notify(
                    'Validé !', type='positive', timeout=5000,
                    actions=[{'label': 'ANNULER', 'color': 'white',
                              'handler': lambda: asyncio.create_task(_undo())}],
                )

            ui.button(icon='check', on_click=_validate).props('flat round dense').classes(
                'text-green-500').tooltip('Marquer comme révisé')
```

- [ ] **Step 2: Verify module import**

Run: `python -c "import frontend.pages.todo"`
Expected: no error

- [ ] **Step 3: Commit**

```bash
git add frontend/pages/todo.py
git commit -m "feat: add undo action to course validation toast"
```

---

## Task 7: Add `_get_day_summary` and `_get_yesterday_carryover` async orchestrators

**Files:**
- Modify: `frontend/pages/todo.py`

**Interfaces:**
- Consumes: `_DaySummary` (Task 2), `_compute_ajoute_progress` (Task 1), `_compute_carryover` (Task 3), `_get_routine_summary` (Task 5).
- Produces: `_get_day_summary(date_obj, cache) -> _DaySummary` (async), `_get_yesterday_carryover(date_obj) -> list[str]` (async). Used by Task 9 (week strip enrichment) and Task 8 (hero carryover badge).

No dedicated unit test (async Notion orchestration, no async test infra in this repo — same rationale as Task 4).

- [ ] **Step 1: Add both functions**

In `frontend/pages/todo.py`, add near `_load_and_render_network_blocs`:

```python
async def _get_day_summary(date_obj: datetime.date, cache: dict) -> "_DaySummary":
    """Résout (et met en cache) le résumé complet (routine + ajouté) d'une date.
    Ne refait jamais l'appel Notion si ajoute_loaded est déjà True pour cette date."""
    date_str = date_obj.isoformat()
    summary = cache.get(date_str)
    if summary is None:
        summary = _get_routine_summary(date_obj)
        cache[date_str] = summary
    if summary.ajoute_loaded:
        return summary

    task = await notion_service.get_daily_task_by_date(date_obj)
    reviewed_titles: list[str] = []
    manual_titles: list[str] = []
    if task:
        reviewed_titles, manual_titles = await asyncio.gather(
            notion_service.get_daily_reviewed_courses(task.id),
            notion_service.get_daily_manual_revision_courses(task.id),
        )
    events = await calendar_service.get_events_for_day(date_obj)
    course_items = _build_course_list(events, manual_titles, data_store.cours)
    dynamic_tasks = task.dynamic_checkboxes if task else {}

    summary.ajoute_total, summary.ajoute_done = _compute_ajoute_progress(
        course_items, reviewed_titles, dynamic_tasks)
    summary.ajoute_loaded = True
    return summary


async def _get_yesterday_carryover(date_obj: datetime.date) -> list[str]:
    """Cours manuels programmés hier et non marqués révisés (lecture seule, pas de déplacement)."""
    if date_obj != datetime.date.today():
        return []
    yesterday = date_obj - datetime.timedelta(days=1)
    task = await notion_service.get_daily_task_by_date(yesterday)
    if not task:
        return []
    reviewed_titles, manual_titles = await asyncio.gather(
        notion_service.get_daily_reviewed_courses(task.id),
        notion_service.get_daily_manual_revision_courses(task.id),
    )
    return _compute_carryover(manual_titles, reviewed_titles)
```

- [ ] **Step 2: Verify module import**

Run: `python -c "import frontend.pages.todo"`
Expected: no error

- [ ] **Step 3: Commit**

```bash
git add frontend/pages/todo.py
git commit -m "feat: add async day-summary and yesterday-carryover orchestrators"
```

---

## Task 8: CSS — week strip day pills

**Files:**
- Modify: `static/synapse.css` (append after the "QCM PAGE REDESIGN" section, end of file)

**Interfaces:**
- Produces: CSS classes `.todo-week-strip`, `.todo-day-pill` (+ `.active`), `.todo-day-pill-name`, `.todo-day-pill-num`, `.todo-day-pill-bar`, `.todo-day-pill-bar-fill`. Used by Task 9.

- [ ] **Step 1: Append the CSS block**

Add at the end of `static/synapse.css`:

```css
/* ═══════════════════════════════════════════════════════════════
   TODO — WEEK STRIP
   ═══════════════════════════════════════════════════════════════ */

.todo-week-strip {
  display: flex;
  gap: 8px;
  width: 100%;
}

.todo-day-pill {
  flex: 1 1 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 10px 4px 8px;
  border-radius: var(--s-r-lg);
  border: 1px solid var(--s-border);
  background: #FFFFFF;
  cursor: pointer;
  user-select: none;
  transition: border-color 160ms ease, background 160ms ease, transform 160ms ease;
}
.todo-day-pill:hover {
  border-color: #CBD5E1;
  transform: translateY(-1px);
}
.todo-day-pill.active {
  border-color: var(--s-primary-600);
  background: var(--s-primary-50);
}
body.body--dark .todo-day-pill {
  background: #111827;
  border-color: #1E2D3D;
}
body.body--dark .todo-day-pill.active {
  border-color: #93C5FD;
  background: rgba(37,99,235,0.12);
}

.todo-day-pill-name {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--s-text-400);
}
.todo-day-pill.active .todo-day-pill-name { color: var(--s-primary-600); }
body.body--dark .todo-day-pill.active .todo-day-pill-name { color: #93C5FD; }

.todo-day-pill-num {
  font-family: var(--s-font-body);
  font-size: 15px;
  font-weight: 700;
  color: var(--s-text-900);
}

.todo-day-pill-bar {
  height: 3px;
  width: 100%;
  border-radius: 99px;
  background: var(--s-bg-muted);
  overflow: hidden;
}
.todo-day-pill-bar-fill {
  height: 100%;
  border-radius: 99px;
  transition: width 400ms ease-out;
}
```

- [ ] **Step 2: Commit**

```bash
git add static/synapse.css
git commit -m "style: add week-strip day pill classes to synapse.css"
```

---

## Task 9: Hero banner — nav row + stats row

**Files:**
- Modify: `frontend/pages/todo.py` (add new functions, remove old header code from `todo_page` in Task 14)

**Interfaces:**
- Consumes: `_DaySummary` cache (Task 2/5), `_fmt_date`, `local_store.get_streak_days`.
- Produces: `_render_hero_nav(container, state) -> dict` (button refs), `_wire_nav_handlers(refs, render_day, state, on_date_click)`, `_update_header(refs, state)`, `_pill_color(summary) -> str`, `_render_hero_stats(container, state, cache, carryover_holder)`. Used by Task 14 (assembly) and Task 11 (`_pill_color` reused by the strip).

No dedicated unit test: pure NiceGUI rendering, verified manually in Task 14.

- [ ] **Step 1: Add `_pill_color`**

In `frontend/pages/todo.py`, add near `_DaySummary`:

```python
def _pill_color(summary: "_DaySummary") -> str:
    if summary.total == 0:
        return '#CBD5E1'
    if summary.pct >= 1.0:
        return '#059669'
    return '#2563EB'
```

- [ ] **Step 2: Add `_render_hero_nav`, `_wire_nav_handlers`, `_update_header`**

Add these functions (they replace the inline header-building code currently in `todo_page`, lines 404-416 and 448-456):

```python
def _render_hero_nav(container: ui.column, state: dict) -> dict:
    """Ligne de navigation date du hero. Reconstruite à chaque changement de jour."""
    container.clear()
    refs = {}
    with container:
        with ui.row().classes('w-full items-center gap-1'):
            refs['prev'] = ui.button(icon='chevron_left').props('flat round dense')
            with ui.row().classes('items-center gap-1 flex-1 justify-center'):
                refs['hier'] = ui.button('Hier').props('flat dense size=sm rounded')
                refs['auj']  = ui.button("Auj.").props('flat dense size=sm rounded')
                refs['dem']  = ui.button('Demain').props('flat dense size=sm rounded')
            refs['date_btn'] = ui.button(_fmt_date(state['date'])).props('flat dense').classes(
                'font-semibold text-slate-700 dark:text-slate-100 min-w-[190px] text-sm')
            refs['next'] = ui.button(icon='chevron_right').props('flat round dense')
    return refs


def _wire_nav_handlers(refs: dict, render_day, state: dict, on_date_click) -> None:
    today = datetime.date.today()
    refs['prev'].on('click', lambda: asyncio.create_task(
        render_day(state['date'] - datetime.timedelta(days=1))))
    refs['next'].on('click', lambda: asyncio.create_task(
        render_day(state['date'] + datetime.timedelta(days=1))))
    refs['hier'].on('click', lambda: asyncio.create_task(
        render_day(today - datetime.timedelta(days=1))))
    refs['auj'].on('click', lambda: asyncio.create_task(render_day(today)))
    refs['dem'].on('click', lambda: asyncio.create_task(
        render_day(today + datetime.timedelta(days=1))))
    refs['date_btn'].on('click', on_date_click)


def _update_header(refs: dict, state: dict) -> None:
    today = datetime.date.today()
    d = state['date']
    for btn, delta in [(refs['hier'], -1), (refs['auj'], 0), (refs['dem'], 1)]:
        if d == today + datetime.timedelta(days=delta):
            btn.props(remove='flat').props('unelevated color=primary size=sm rounded')
        else:
            btn.props(remove='unelevated color=primary').props('flat size=sm rounded')
```

- [ ] **Step 3: Add `_render_hero_stats`**

```python
def _render_hero_stats(
    container: ui.row,
    state: dict,
    cache: dict,
    carryover_holder: dict,
) -> None:
    container.clear()
    date_str = state['date'].isoformat()
    summary = cache.get(date_str, _DaySummary())
    pct = summary.pct
    color = _pill_color(summary)
    streak = local_store.get_streak_days()
    carryover = carryover_holder.get(date_str, [])

    with container:
        with ui.element('div').classes('synapse-ring').style(
                f'--ring-pct:{pct * 100};--ring-color:{color}'):
            ui.label(f'{int(pct * 100)}%').classes('synapse-ring-label').style(f'color:{color}')

        if streak > 0:
            with ui.row().classes('items-center gap-1'):
                ui.icon('local_fire_department',
                        color='orange-6' if streak >= 3 else 'amber-6', size='sm')
                ui.label(f'{streak}j').classes(
                    'text-sm font-bold text-slate-600 dark:text-slate-300')

        if carryover:
            with ui.row().classes(
                    'items-center gap-1 px-2 py-1 rounded-full cursor-pointer '
                    'bg-amber-50 dark:bg-amber-900/20'
            ).tooltip(', '.join(carryover)):
                ui.icon('history', color='amber-7', size='xs')
                ui.label(f"{len(carryover)} reporté(s) d'hier").classes(
                    'text-xs font-semibold text-amber-700 dark:text-amber-400')
```

- [ ] **Step 4: Verify module import**

Run: `python -c "import frontend.pages.todo"`
Expected: no error

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/todo.py
git commit -m "feat: add hero nav row and hero stats row renderers"
```

---

## Task 10: Week strip renderer + background enrichment loop

**Files:**
- Modify: `frontend/pages/todo.py`

**Interfaces:**
- Consumes: `_week_dates`, `_DaySummary`, `_pill_color` (Task 9), `_get_day_summary` (Task 7), `.todo-week-strip`/`.todo-day-pill` CSS (Task 8).
- Produces: `_render_week_strip(container, week, active_date, cache, on_pick_day)`, `_load_week_ajoute(week, cache, redraw)` (async). Used by Task 14.

No dedicated unit test: NiceGUI rendering + async orchestration, verified manually in Task 14 (confirm the 7 pills render immediately with routine data, then fill in with Ajouté data progressively).

- [ ] **Step 1: Add `_render_week_strip`**

```python
def _render_week_strip(
    container: ui.row,
    week: list[datetime.date],
    active_date: datetime.date,
    cache: dict,
    on_pick_day,
) -> None:
    container.clear()
    with container:
        with ui.element('div').classes('todo-week-strip'):
            for d in week:
                summary = cache.get(d.isoformat(), _DaySummary())
                pct = summary.pct
                color = _pill_color(summary)
                is_active = d == active_date

                cls = 'todo-day-pill active' if is_active else 'todo-day-pill'
                with ui.element('div').classes(cls).on(
                        'click', lambda _e, dd=d: asyncio.create_task(on_pick_day(dd))):
                    ui.label(_DAYS[d.weekday()]).classes('todo-day-pill-name')
                    ui.label(str(d.day)).classes('todo-day-pill-num')
                    with ui.element('div').classes('todo-day-pill-bar'):
                        ui.element('div').classes('todo-day-pill-bar-fill').style(
                            f'width:{int(pct * 100)}%;background:{color}')
```

- [ ] **Step 2: Add `_load_week_ajoute`**

```python
async def _load_week_ajoute(week: list[datetime.date], cache: dict, redraw) -> None:
    """Enrichit chaque pastille avec les données Ajouté (Notion), une par une
    (throttle volontaire : jamais en parallèle)."""
    for d in week:
        summary = cache.get(d.isoformat())
        if summary and summary.ajoute_loaded:
            continue
        await _get_day_summary(d, cache)
        redraw()
```

- [ ] **Step 3: Verify module import**

Run: `python -c "import frontend.pages.todo"`
Expected: no error

- [ ] **Step 4: Commit**

```bash
git add frontend/pages/todo.py
git commit -m "feat: add week strip renderer with progressive background enrichment"
```

---

## Task 11: Empty-state CTA and quick-add repositioning

**Files:**
- Modify: `frontend/pages/todo.py` (`_render_ajout_block`, inside the function rewritten in Task 5)

**Interfaces:**
- Consumes: `_open_add_course_dialog` (existing, unchanged signature).
- Produces: same `_render_ajout_block` signature as Task 5, visual/behavioral change only inside the function body.

- [ ] **Step 1: Move the quick-add controls above the list and add the empty-state CTA**

In `frontend/pages/todo.py`, replace the body of `_render_ajout_block` (from Task 5, inside the `with ui.column().classes('flex-1 gap-2'):` block) with this reordered version:

```python
async def _render_ajout_block(
    container: ui.column,
    date_obj: datetime.date,
    task,
    course_items: list[dict],
    reviewed_titles: list[str],
    cache: dict,
    on_update,
) -> None:
    date_str = date_obj.isoformat()
    dynamic_tasks = task.dynamic_checkboxes if task else {}
    ajoute_total, ajoute_done = _compute_ajoute_progress(course_items, reviewed_titles, dynamic_tasks)

    summary = cache[date_str]
    summary.ajoute_total = ajoute_total
    summary.ajoute_done = ajoute_done
    summary.ajoute_loaded = True

    container.clear()
    with container:
        with ui.row().classes('w-full gap-4 items-start'):
            ui.element('div').classes('w-1 rounded-full bg-violet-500 self-stretch min-h-[2rem]')
            with ui.column().classes('flex-1 gap-2'):
                ui.label('AJOUTÉ').classes(
                    'text-xs font-bold uppercase tracking-widest text-slate-400 mb-1')

                # ── Contrôles d'ajout — en haut, avant la liste ────────────────
                with ui.row().classes('items-center gap-2 pb-2'):
                    ui.button('+ Cours', icon='add',
                              on_click=lambda: _open_add_course_dialog(date_obj, task)).props(
                        'unelevated dense rounded').classes(
                        'bg-violet-600 text-white text-sm font-medium')

                    new_task_input = ui.input(placeholder='+ Tâche libre…').props(
                        'borderless dense').classes('flex-1 text-sm text-slate-600 dark:text-slate-300')

                    async def _add_task_free():
                        val = new_task_input.value.strip()
                        if not val or not task:
                            return
                        new_task_input.value = ''
                        if await notion_service.add_dynamic_task(task.id, val):
                            ui.notify('Tâche ajoutée', type='positive')
                            updated = await notion_service.get_daily_task_by_date(date_obj)
                            if updated and not container.is_deleted:
                                await _render_ajout_block(
                                    container, date_obj, updated, course_items,
                                    reviewed_titles, cache, on_update,
                                )

                    new_task_input.on('keydown.enter',
                                      lambda: asyncio.create_task(_add_task_free()))
                    ui.button(icon='send',
                              on_click=lambda: asyncio.create_task(_add_task_free())).props(
                        'flat round dense').classes('text-violet-500')

                # ── Cours ─────────────────────────────────────────────────────
                for item in course_items:
                    _render_course_item(
                        item['course'], item['course'].title in reviewed_titles,
                        item['type'], task, cache, date_str, on_update,
                    )

                # ── Tâches dynamiques ─────────────────────────────────────────
                for b_id, data in dynamic_tasks.items():
                    async def _toggle_dyn(e, bid=b_id):
                        delta = 1 if e.value else -1
                        summary.ajoute_done = max(
                            0, min(summary.ajoute_total, summary.ajoute_done + delta))
                        on_update()
                        await notion_service.toggle_dynamic_task(bid, e.value)

                    ui.checkbox(data['text'], value=data['checked'],
                                on_change=_toggle_dyn).props('dense').classes(
                        'text-slate-700 dark:text-slate-200')

                # ── État vide ─────────────────────────────────────────────────
                if not course_items and not dynamic_tasks:
                    with ui.column().classes('w-full items-center gap-1 py-4'):
                        ui.icon('event_available', size='md').classes('text-slate-300 dark:text-slate-600')
                        ui.label('Rien de planifié pour ce jour').classes(
                            'text-sm text-slate-400 italic')
                        ui.button('+ Ajouter un cours',
                                  on_click=lambda: _open_add_course_dialog(date_obj, task)).props(
                            'flat dense').classes(
                            'text-violet-600 dark:text-violet-400 text-sm font-medium mt-1')
```

- [ ] **Step 2: Verify module import**

Run: `python -c "import frontend.pages.todo"`
Expected: no error

- [ ] **Step 3: Commit**

```bash
git add frontend/pages/todo.py
git commit -m "feat: reposition quick-add above the list and add empty-state CTA"
```

---

## Task 12: Panels — convert the 3 blocks to `.synapse-panel` / `.synapse-section-label`

**Files:**
- Modify: `frontend/pages/todo.py` (`_render_routine_block`, `_render_ajout_block`, `_render_note_block`, `_render_skeleton_bloc`)

**Interfaces:** none new — visual-only change, same signatures as Tasks 5/6/11.

- [ ] **Step 1: Update `_render_routine_block`**

Replace the `with ui.row()...` wrapper in `_render_routine_block` (from Task 5) with a `.synapse-panel`:

```python
def _render_routine_block(
    container: ui.column,
    date_str: str,
    cache: dict,
    on_update,
) -> None:
    items  = local_store.get_routine_items()
    checks = local_store.get_routine_checks(date_str)
    summary = cache[date_str]

    with container:
        with ui.element('div').classes('synapse-panel w-full p-4'):
            ui.label('ROUTINE').classes('synapse-section-label mb-2')
            with ui.element('div').classes(
                    'grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-2'):
                for name in items:
                    checked = checks.get(name, False)

                    def _on_toggle(e, item_name=name):
                        delta = 1 if e.value else -1
                        summary.routine_done = max(
                            0, min(summary.routine_total, summary.routine_done + delta))
                        on_update()
                        local_store.set_routine_check(date_str, item_name, e.value)

                    ui.checkbox(name, value=checked, on_change=_on_toggle).props('dense').classes(
                        'text-slate-700 dark:text-slate-200 transition-opacity duration-200')

    on_update()
```

- [ ] **Step 2: Update `_render_ajout_block`**

In the version from Task 11, replace:

```python
        with ui.row().classes('w-full gap-4 items-start'):
            ui.element('div').classes('w-1 rounded-full bg-violet-500 self-stretch min-h-[2rem]')
            with ui.column().classes('flex-1 gap-2'):
                ui.label('AJOUTÉ').classes(
                    'text-xs font-bold uppercase tracking-widest text-slate-400 mb-1')
```

with:

```python
        with ui.element('div').classes('synapse-panel w-full p-4'):
            ui.label('AJOUTÉ').classes('synapse-section-label mb-2')
```

(remove the now-unneeded closing of the old `ui.row`/inner `ui.column` — the rest of the function body keeps its indentation under this single `with` block instead of two nested ones.)

- [ ] **Step 3: Update `_render_note_block`**

Replace the full function (lines 336-386 of the original file) with:

```python
def _render_note_block(
    container: ui.column,
    task,
    is_past: bool,
) -> None:
    container.clear()
    with container:
        with ui.element('div').classes('synapse-panel w-full p-4'):
            ui.label('NOTE DU JOUR').classes('synapse-section-label mb-2')

            if is_past:
                ui.label('Journée passée — notes visibles dans Notion.').classes(
                    'text-sm italic text-slate-400')
                return

            note_ta = ui.textarea(
                placeholder='Comment s\'est passée la journée ?'
            ).props('outlined rows=2 autogrow').classes('w-full text-sm')

            save_row = ui.row().classes('w-full justify-end hidden')
            with save_row:
                save_btn = ui.button('Enregistrer').props(
                    'unelevated dense rounded').classes(
                    'bg-amber-500 text-white text-sm')

            def _on_input(e):
                if e.value.strip():
                    save_row.classes(remove='hidden')
                else:
                    save_row.classes(add='hidden')

            note_ta.on('update:model-value', _on_input)

            async def _save():
                val = note_ta.value.strip()
                if not val:
                    return
                if not task:
                    ui.notify('Pas de fiche pour ce jour', type='warning')
                    return
                note_ta.value = ''
                save_row.classes(add='hidden')
                if await notion_service.add_daily_comment(task.id, val):
                    ui.notify('Note enregistrée', type='positive')
                else:
                    ui.notify('Erreur Notion', type='negative')

            save_btn.on('click', lambda: asyncio.create_task(_save()))
```

- [ ] **Step 4: Update `_render_skeleton_bloc` to match the panel look**

Replace the full function with:

```python
def _render_skeleton_bloc(container: ui.column, marker_css: str, title: str) -> None:
    container.clear()
    with container:
        with ui.element('div').classes('synapse-panel w-full p-4'):
            ui.label(title).classes('synapse-section-label mb-2')
            for w in ['w-3/4', 'w-1/2', 'w-2/3']:
                ui.element('div').classes(
                    f'h-5 rounded-md animate-pulse bg-slate-200 dark:bg-slate-700 {w}')
```

(`marker_css` parameter is now unused by the body but kept in the signature — call sites in `_load_and_render_network_blocs` pass `'bg-violet-500'` / `'bg-amber-500'` and don't need updating.)

- [ ] **Step 5: Verify module import**

Run: `python -c "import frontend.pages.todo"`
Expected: no error

- [ ] **Step 6: Commit**

```bash
git add frontend/pages/todo.py
git commit -m "style: convert Routine/Ajouté/Note blocks to synapse-panel"
```

---

## Task 13: Final assembly — `todo_page()`

**Files:**
- Modify: `frontend/pages/todo.py:389-493` (`todo_page`)

**Interfaces:** none new — wires together every function from Tasks 1-12.

- [ ] **Step 1: Rewrite `todo_page`**

Replace the full function (lines 389-493) with:

```python
async def todo_page():
    with frame("Suivi Quotidien"):
        state: dict = {'date': datetime.date.today()}
        cache: dict = {}
        carryover_holder: dict = {}
        week = _week_dates(datetime.date.today())

        # Pré-remplit le cache avec la routine (instantané, local) pour les 7 jours
        # de la strip, avant le premier rendu — sans ça, les pastilles autres que
        # "aujourd'hui" resteraient vides jusqu'à ce que _load_week_ajoute les atteigne
        # séquentiellement (spec section 3 : la routine doit être immédiate pour les 7 jours).
        for _d in week:
            cache[_d.isoformat()] = _get_routine_summary(_d)

        # ── Hero (sticky) ───────────────────────────────────────────────────────
        with ui.element('div').classes(
                'synapse-hero flex-col gap-3 items-stretch w-full'
        ).style('position: sticky; top: 0; z-index: 10;'):
            nav_container   = ui.column().classes('w-full gap-0')
            stats_container = ui.row().classes('w-full items-center gap-4')

        # ── Strip 7 jours ──────────────────────────────────────────────────────
        strip_container = ui.row().classes('w-full mt-3')

        # ── Zone de contenu ────────────────────────────────────────────────────
        content = ui.column().classes('w-full px-4 py-5 gap-6')

        # ── Helpers ────────────────────────────────────────────────────────────
        def _refresh_stats():
            _render_hero_stats(stats_container, state, cache, carryover_holder)

        def _draw_strip():
            _render_week_strip(strip_container, week, state['date'], cache, _render_day)

        def _open_date_picker():
            with ui.dialog() as dlg, ui.card().classes('items-center gap-3 p-4'):
                dp = ui.date(value=state['date'].isoformat()).props('no-unset')
                async def _confirm():
                    if dp.value:
                        dlg.close()
                        await _render_day(datetime.date.fromisoformat(dp.value))
                ui.button('OK', on_click=_confirm).props('unelevated color=primary rounded')
            dlg.open()

        async def _load_carryover(date_obj: datetime.date):
            titles = await _get_yesterday_carryover(date_obj)
            carryover_holder[date_obj.isoformat()] = titles
            if date_obj == state['date']:
                _refresh_stats()

        async def _render_day(date_obj: datetime.date):
            state['date'] = date_obj

            nav_refs = _render_hero_nav(nav_container, state)
            _wire_nav_handlers(nav_refs, _render_day, state, _open_date_picker)
            _update_header(nav_refs, state)

            # Rafraîchit la routine dans le cache AVANT le premier affichage des stats/strip,
            # sinon la ligne hero et la strip liraient un _DaySummary manquant ou périmé
            # (celui d'une date jamais visitée, ou d'un ancien jour) pendant l'instant
            # qui précède la résolution de _render_content.
            _refresh_routine_in_cache(date_obj, cache)
            _refresh_stats()
            _draw_strip()

            asyncio.create_task(_load_carryover(date_obj))
            await _render_content(content, date_obj, cache, _refresh_stats)
            _refresh_stats()
            _draw_strip()

        # ── Démarrage ──────────────────────────────────────────────────────────
        ui.timer(0.1, lambda: asyncio.create_task(
            _render_day(datetime.date.today())), once=True)
        ui.timer(0.5, lambda: asyncio.create_task(
            _load_week_ajoute(week, cache, _draw_strip)), once=True)
```

- [ ] **Step 2: Run the full test suite**

Run: `python -m pytest tests/test_todo_logic.py -v`
Expected: all 24 tests PASS

Run: `python -c "import frontend.pages.todo"`
Expected: no error

- [ ] **Step 3: Commit**

```bash
git add frontend/pages/todo.py
git commit -m "refactor: assemble hero, week strip, and content into todo_page()"
```

---

## Task 14: Manual verification pass

**Files:** none (verification only)

- [ ] **Step 1: Start the app**

Run: `python main.py` (or the project's existing local-run command — check `README.md` / `CLAUDE.md` if `main.py` requires arguments)

- [ ] **Step 2: Full test suite**

Run: `python -m pytest tests/ -v`
Expected: all tests PASS, no regressions in unrelated test files (`test_local_store.py`, `test_notion_payloads.py`, etc.)

- [ ] **Step 3: Browser checklist on `/todo`**

Open `http://127.0.0.1:8082/todo` (or the port the app prints on startup) in light mode, then switch to dark mode and repeat:

- [ ] Hero banner shows date, ring %, streak flame (if streak > 0), sticky on scroll.
- [ ] Week strip shows 7 pills, today highlighted; pills fill in with Ajouté data a moment after load (not just routine).
- [ ] Clicking a different pill navigates to that day and updates the hero + content.
- [ ] Hier / Auj. / Demain / ◀ ▶ / date picker all still navigate correctly.
- [ ] Routine checkboxes toggle instantly and update the hero ring.
- [ ] A day with nothing planned in Ajouté shows the empty-state icon + message + "+ Ajouter un cours" button, and clicking it opens the existing course dialog.
- [ ] Quick-add ("+ Cours" and free-text input) appear at the top of the Ajouté panel, above the list.
- [ ] Validating a course shows a "Validé !" toast with an "ANNULER" action; clicking it within 5s reverts the course to unvalidated and decrements the ring.
- [ ] On today, if yesterday has unfinished manual courses, the "N reporté(s) d'hier" badge appears in the hero with a tooltip listing the titles; navigating to a different day hides it.
- [ ] All 3 blocks (Routine / Ajouté / Note du jour) render as `.synapse-panel` cards, no colored left bar remaining.
- [ ] No console errors in the browser dev tools during the above interactions.

- [ ] **Step 4: Commit any fixups found during manual verification**

If the manual pass surfaces issues, fix them and commit with a descriptive message (e.g. `fix: correct hero ring color threshold found during manual QA`).

---

## Spec coverage check

| Spec section | Task(s) |
|---|---|
| 1. `_DaySummary` cache | 2, 5, 7 |
| 2. Hero banner | 9, 13 |
| 3. Strip 7 jours | 8, 10, 13 |
| 4. Panels neutres | 12 |
| 5. Signal reporté d'hier | 7, 9, 13 |
| 6. État vide avec CTA | 11 |
| 7. Ajout rapide remonté | 11 |
| 8. Undo sur validation | 4, 6 |
| 9. Additions backend | 4 |
| 10. Vérification | 14 |
