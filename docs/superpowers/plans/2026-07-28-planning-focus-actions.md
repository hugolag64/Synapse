# Planning focus and day actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a useful “Focus de la semaine” section, make item titles readable at every planning density, and let a day create either a local Synapse planning entry or a Google Calendar event.

**Architecture:** Keep `frontend/pages/planning_cockpit.py` as the view orchestrator, add pure planning-entry helpers for validation/formatting, and persist manual Synapse entries in the existing SQLite local store. Google Calendar remains the source of truth for personal events; the existing `calendar_service.create_event()` creates them in `primary`, while manual Synapse entries never mutate review due dates.

**Tech Stack:** Python 3, NiceGUI, SQLite via `backend.core.reviews.local_store`, existing Google Calendar API wrapper, pytest.

## Global Constraints

- The main Planning grid remains the primary visual surface.
- Add one compact block below it titled `Focus de la semaine`.
- Clicking a day opens a centered action modal with `Planifier un item Synapse` and `Créer un événement Google Calendar`.
- Manual Synapse planning entries are local and never modify `due_date`, mastery, Notion, or review history.
- Google Calendar events are created in the existing `primary` calendar and are not duplicated into local planning storage.
- View 7j titles show at most 2 lines, 3j titles at most 3 lines, and 1j titles wrap naturally; every truncated title has a tooltip.
- Animations are short and non-essential: modal scale/fade, focus row hover, and new-entry appearance.
- Calendar creation failure must show an error and must not leave a local event placeholder.

---

### Task 1: Persist manual Synapse planning entries

**Files:**
- Modify: `backend/core/reviews/local_store.py:init_db` and add planning-entry functions
- Create: `tests/test_manual_planning_store.py`

**Interfaces:**
- Consumes: `datetime.date`, course identity/title, activity type, duration.
- Produces:
  - `create_manual_planning_entry(entry_date, course_id, course_title, item_number, activity_type, duration_minutes) -> dict`
  - `get_manual_planning_entries(start_date, end_date) -> list[dict]`
  - `delete_manual_planning_entry(entry_id) -> bool`

- [ ] **Step 1: Write failing tests for create/read/delete and due-date independence.**

```python
def test_manual_planning_entry_round_trip_and_delete(tmp_path, monkeypatch):
    import datetime
    from backend.core.reviews import local_store

    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "planning.db")
    local_store._DB = None
    local_store.init_db()
    created = local_store.create_manual_planning_entry(
        datetime.date(2026, 7, 28), "course-1", "Syphilis", "162", "qcm", 30
    )
    rows = local_store.get_manual_planning_entries(
        datetime.date(2026, 7, 28), datetime.date(2026, 7, 28)
    )
    assert rows[0]["id"] == created["id"]
    assert rows[0]["activity_type"] == "qcm"
    assert rows[0]["duration_minutes"] == 30
    assert local_store.delete_manual_planning_entry(created["id"])
    assert local_store.get_manual_planning_entries(
        datetime.date(2026, 7, 28), datetime.date(2026, 7, 28)
    ) == []
```

- [ ] **Step 2: Run the focused test and verify the table/functions are missing.**

Run: `python -m pytest tests/test_manual_planning_store.py -v`

Expected: FAIL because the planning table/functions do not exist.

- [ ] **Step 3: Add the SQLite table and CRUD functions.**

Create this table in `init_db()`:

```sql
CREATE TABLE IF NOT EXISTS manual_planning_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date TEXT NOT NULL,
    course_id TEXT NOT NULL,
    course_title TEXT NOT NULL DEFAULT '',
    item_number TEXT NOT NULL DEFAULT '',
    activity_type TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_manual_planning_date
    ON manual_planning_entries(entry_date);
```

Validate activity types against `{"revision", "lecture", "qcm", "lacune"}`, clamp duration to a positive integer, use ISO dates, and return dictionaries rather than live SQLite rows. `get_manual_planning_entries` must include both endpoints.

- [ ] **Step 4: Run the focused store tests and the existing local-store tests.**

Run: `python -m pytest tests/test_manual_planning_store.py tests/test_local_store.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the persistence unit.**

```bash
git add backend/core/reviews/local_store.py tests/test_manual_planning_store.py
git commit -m "feat(planning): persist manual planning entries locally"
```

### Task 2: Add pure focus rows and responsive item-title presentation

**Files:**
- Create: `backend/core/planning/focus.py`
- Create: `tests/test_planning_focus.py`
- Modify: `frontend/pages/planning_cockpit.py:_CSS` and `_draw_day`

**Interfaces:**
- Consumes: plans and review tasks.
- Produces: `build_focus_rows(plans, all_tasks) -> list[dict]` with stable row kinds `overdue`, `next_session`, and `free_slots`.

- [ ] **Step 1: Write failing tests for focus-row content.**

```python
def test_build_focus_rows_prioritizes_overdue_then_next_session():
    from types import SimpleNamespace
    from backend.core.planning.focus import build_focus_rows

    plans = [SimpleNamespace(total_min=30), SimpleNamespace(total_min=0)]
    tasks = [SimpleNamespace(days_overdue=2), SimpleNamespace(days_overdue=0)]
    rows = build_focus_rows(plans, tasks)
    assert [row["kind"] for row in rows] == ["overdue", "next_session", "free_slots"]
    assert rows[0]["value"] == 1
    assert rows[2]["value"] == 1
```

- [ ] **Step 2: Run the focused test and verify the helper is missing.**

Run: `python -m pytest tests/test_planning_focus.py -v`

Expected: FAIL with an import error.

- [ ] **Step 3: Implement `build_focus_rows`.**

Return exactly three rows: overdue count, next non-empty plan total in minutes, and empty-plan count. Use `0` values rather than omitting rows so the UI layout remains stable.

- [ ] **Step 4: Add title wrapping and tooltip behavior.**

Replace the current single-line rule:

```css
.pl-block-title { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
```

with density-specific classes:

```css
.pl-block-title { overflow:hidden; display:-webkit-box; -webkit-box-orient:vertical; }
.pl-grid[data-days="7"] .pl-block-title { -webkit-line-clamp:2; }
.pl-grid[data-days="3"] .pl-block-title { -webkit-line-clamp:3; }
.pl-grid[data-days="1"] .pl-block-title { white-space:normal; }
```

Set `data-days` on the grid when rendering the skeleton. Attach the full title as a NiceGUI tooltip to each item/event block, and keep metadata in `.pl-block-sub` below the title.

- [ ] **Step 5: Run focus/title tests and compile.**

Run: `python -m pytest tests/test_planning_focus.py -v` and `python -m compileall backend/core/planning/focus.py frontend/pages/planning_cockpit.py -q`.

Expected: PASS and successful compilation.

- [ ] **Step 6: Commit focus and readability.**

```bash
git add backend/core/planning/focus.py tests/test_planning_focus.py frontend/pages/planning_cockpit.py
git commit -m "feat(planning): add focus summary and readable item titles"
```

### Task 3: Render Focus de la semaine below the grid

**Files:**
- Modify: `frontend/pages/planning_cockpit.py:render_planning_cockpit`, `_draw_topbar`, `_load_and_render`
- Test: `tests/test_planning_focus.py`

**Interfaces:**
- Consumes: `build_focus_rows`, active lacunes, and existing planning navigation.
- Produces: one compact below-grid focus block with clickable rows and Linear-style hover/entry animations.

- [ ] **Step 1: Add a pure label test for focus rows.**

```python
def test_focus_labels_are_actionable_and_stable():
    from backend.core.planning.focus import focus_row_label
    assert focus_row_label({"kind": "overdue", "value": 3}) == "3 révisions en retard"
    assert focus_row_label({"kind": "free_slots", "value": 2}) == "2 créneaux libres à utiliser"
```

- [ ] **Step 2: Implement `focus_row_label`.**

Handle singular/plural forms for the three row kinds, including `0`, and keep all copy in French.

- [ ] **Step 3: Render the block after the legend.**

Use a two-column compact card only on desktop and one column below the mobile breakpoint. Render one row per focus item with a subtle `transition`/hover background. Keep the block visually lighter than the planning grid: border, muted labels, one indigo action badge.

- [ ] **Step 4: Wire focus rows to existing actions.**

Clicking `overdue` navigates to `/todo`; clicking `next_session` keeps the current planning view but opens the day-action modal for the first non-empty day; clicking `free_slots` focuses the first empty day. Do not introduce a second statistics dashboard.

- [ ] **Step 5: Run the focus tests and compile.**

Run: `python -m pytest tests/test_planning_focus.py -v` and `python -m compileall frontend/pages/planning_cockpit.py -q`.

Expected: PASS.

- [ ] **Step 6: Commit the Focus block.**

```bash
git add frontend/pages/planning_cockpit.py backend/core/planning/focus.py tests/test_planning_focus.py
git commit -m "feat(planning): add actionable weekly focus block"
```

### Task 4: Add the day action modal and manual item flow

**Files:**
- Modify: `frontend/pages/planning_cockpit.py:_draw_skeleton`, `_draw_day`, new day-action helpers
- Modify: `frontend/components/item_search_palette.py` only if its search helper needs a reusable result renderer
- Test: `tests/test_manual_planning_store.py` and `tests/test_planning_focus.py`

**Interfaces:**
- Consumes: `data_store.cours`, existing `search_items`, and manual planning CRUD functions.
- Produces: `open_day_actions(day)`, `open_manual_item_form(day)`, and a saved local entry that appears in the selected day after reload.

- [ ] **Step 1: Add a test that saving an item does not mutate its review date.**

```python
def test_manual_planning_is_independent_from_review_due_date(tmp_path, monkeypatch):
    import datetime
    from backend.core.reviews import local_store
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "planning.db")
    local_store._DB = None
    local_store.init_db()
    due_date = datetime.date(2026, 8, 4)
    local_store.create_manual_planning_entry(
        datetime.date(2026, 7, 28), "course-1", "Syphilis", "162", "revision", 20
    )
    assert due_date == datetime.date(2026, 8, 4)
```

- [ ] **Step 2: Render day click affordances without breaking item/event clicks.**

Make the day header or empty body clickable, not the entire card. Add a compact `+` affordance visible on hover. Item blocks keep their existing item navigation/action; calendar event blocks remain read-only.

- [ ] **Step 3: Implement the centered day-action modal.**

The modal title is the selected French date and contains two prominent buttons: `Planifier un item Synapse` and `Créer un événement Google Calendar`. Add the existing item-search behavior inside the first flow rather than duplicating fuzzy matching.

- [ ] **Step 4: Implement manual item selection and save.**

Show search input, result rows with `ITEM <number>`, title, and college, activity select with `Révision`, `Lecture`, `QCM`, `Lacune`, and a duration number prefilled from the corresponding planning duration preference. On save, call `create_manual_planning_entry`, close the modal, refresh the week, and show a positive notification. Do not call any Notion or review-date mutation API.

- [ ] **Step 5: Include manual entries in `_load_and_render`.**

Fetch the displayed date range through `get_manual_planning_entries`, render each entry as a Synapse task block with a local/manual badge, and include its duration in the day footer without feeding it back into the automatic `plan_day` selection.

- [ ] **Step 6: Run the focused tests and compile.**

Run: `python -m pytest tests/test_manual_planning_store.py tests/test_planning_focus.py -v` and `python -m compileall frontend/pages/planning_cockpit.py -q`.

Expected: PASS.

- [ ] **Step 7: Commit the day modal and manual item flow.**

```bash
git add frontend/pages/planning_cockpit.py backend/core/reviews/local_store.py frontend/components/item_search_palette.py tests/test_manual_planning_store.py tests/test_planning_focus.py
git commit -m "feat(planning): add day actions and manual item scheduling"
```

### Task 5: Add personal Google Calendar event creation

**Files:**
- Modify: `frontend/pages/planning_cockpit.py` event form and refresh flow
- Modify: `backend/core/google/calendar_service.py` only if a typed end-time helper is required
- Create: `tests/test_planning_calendar_actions.py`

**Interfaces:**
- Consumes: selected day and existing `calendar_service.create_event(summary, start_time_iso, duration_minutes, description, color_id, reminders)`.
- Produces: a Google Calendar event in `primary`, with no local placeholder if the API returns `None` or raises.

- [ ] **Step 1: Write failing tests for event payload normalization.**

```python
def test_event_duration_is_end_minus_start():
    import datetime
    from backend.core.planning.calendar_actions import event_duration_minutes
    start = datetime.datetime(2026, 7, 28, 14, 0)
    end = datetime.datetime(2026, 7, 28, 15, 30)
    assert event_duration_minutes(start, end) == 90


def test_event_end_before_start_is_rejected():
    import datetime
    import pytest
    from backend.core.planning.calendar_actions import event_duration_minutes
    with pytest.raises(ValueError):
        event_duration_minutes(datetime.datetime(2026, 7, 28, 15), datetime.datetime(2026, 7, 28, 14))
```

- [ ] **Step 2: Implement pure event validation.**

Create `backend/core/planning/calendar_actions.py` with `event_duration_minutes(start, end) -> int`, rejecting non-positive durations and returning minutes for the existing Calendar API.

- [ ] **Step 3: Implement the event form.**

The form contains title, start time defaulting to the selected day at the next whole hour, end time defaulting to one hour later, and optional description. On submit, call `calendar_service.create_event` with the selected day’s date/time and calculated duration. On `None`/exception, close nothing, show a negative notification, and leave the planning state unchanged.

- [ ] **Step 4: Refresh and show the created event.**

After a successful result, close the modal, call `_load_and_render()`, and notify `Événement ajouté à Google Calendar`. The existing event fetch then renders it as a dashed event block.

- [ ] **Step 5: Add Calendar action tests with a fake service.**

Cover success, `None` result, and raised exception; assert the failure paths do not call manual-entry creation.

- [ ] **Step 6: Run focused tests and compile.**

Run: `python -m pytest tests/test_planning_calendar_actions.py tests/test_manual_planning_store.py -v` and `python -m compileall backend/core/planning/calendar_actions.py frontend/pages/planning_cockpit.py -q`.

Expected: PASS.

- [ ] **Step 7: Commit Google Calendar action.**

```bash
git add backend/core/planning/calendar_actions.py frontend/pages/planning_cockpit.py tests/test_planning_calendar_actions.py
git commit -m "feat(planning): create personal Google Calendar events"
```

### Task 6: End-to-end verification and delivery

**Files:**
- Modify: `docs/PROGRESSION_SESSION_2026-07-28.md` only if the project session log convention requires recording the delivered feature.

- [ ] **Step 1: Run the complete test suite.**

Run: `python -m pytest -q`.

Expected: all tests pass; report only the known existing warning if unchanged.

- [ ] **Step 2: Run compilation and whitespace checks.**

Run: `python -m compileall backend frontend tests -q` and `git diff --check`.

- [ ] **Step 3: Manually verify the Planning cockpit.**

Check views 1j, 3j, and 7j:

1. Focus block appears once below the grid.
2. Long titles wrap at the density-specific limit and reveal a tooltip.
3. Clicking an empty day opens the day-action modal.
4. Saving a manual item displays it locally and leaves its review due date unchanged.
5. Creating a personal event in a test calendar account refreshes the day with a dashed event.
6. Calendar failure shows an error without a phantom entry.
7. Modal/focus/new-entry animations are short and do not block keyboard navigation.

- [ ] **Step 4: Commit the optional session note and inspect final status.**

```bash
git status --short
git add docs/PROGRESSION_SESSION_2026-07-28.md
git commit -m "docs: record planning actions verification"
```

Do not commit generated browser companion files.
