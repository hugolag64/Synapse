# Planning charge and vacation mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Planning cockpit centered and Linear-like, expose a 3–12 h daily capacity, and add temporary reduced-load or diagnostic-only vacation periods with 1/3/5-day shortcuts.

**Architecture:** Keep UI orchestration in `frontend/pages/planning_cockpit.py`, but move date normalization, capacity conversion, vacation-window detection, and effective capacity calculation into a pure planning policy module. Persist the policy through `data_store` preferences, preserving existing `planning_targets` data and minute-based service APIs. Render the return diagnostic as a non-destructive Planning notice derived from the review tasks whose due dates fall in the vacation window; do not delete or mutate source tasks.

**Tech Stack:** Python 3, NiceGUI, existing `PlanningService`, `data_store` preference persistence, pytest.

## Statut de livraison — 28 juillet 2026

Plan exécuté et intégré dans `master`. La capacité 3–12 h, le mode vacances
réduit ou coupure complète avec diagnostic au retour, les raccourcis 1/3/5
jours, le centrage de la grille et la suppression des anciennes cartes basses
sont livrés. Vérification finale de session : **582 tests passés**.

## Global Constraints

- The Planning UI must expose capacity as hours, never as minutes.
- Valid capacity is 3–12 hours/day, stored as minutes for compatibility.
- Vacation has two strategies: `reduced` and `diagnostic_only`.
- Reduced vacation halves capacity by default and never lowers it below 3 hours.
- Diagnostic-only vacation schedules no ordinary work slots during the active window and shows a return diagnostic afterward.
- Vacation shortcuts are 1, 3, and 5 days from today; custom dates use an explicit start/end date.
- Existing tasks are never deleted or have their due dates mutated by vacation mode.
- Remove both lower Planning cards and keep the grid centered for 1-, 3-, and 7-day views.
- Do not change activity-duration preferences or historical study-duration statistics.

---

### Task 1: Add pure Planning capacity and vacation policy helpers

**Files:**
- Create: `backend/core/planning/policy.py`
- Create: `tests/test_planning_policy.py`

**Interfaces:**
- Consumes: persisted preference dictionaries and `datetime.date` values.
- Produces: `clamp_capacity_hours(value) -> int`, `capacity_hours_to_minutes(hours) -> int`, `vacation_end_date(start, duration_days) -> date`, `effective_capacity_minutes(base_minutes, vacation) -> int`, `is_vacation_day(day, vacation) -> bool`, and `vacation_is_expired(vacation, today) -> bool`.

- [ ] **Step 1: Write failing tests for capacity conversion and bounds.**

```python
def test_capacity_is_clamped_to_three_twelve_hours():
    from backend.core.planning.policy import clamp_capacity_hours
    assert clamp_capacity_hours(1) == 3
    assert clamp_capacity_hours(8) == 8
    assert clamp_capacity_hours(99) == 12


def test_capacity_converts_hours_to_existing_minute_api():
    from backend.core.planning.policy import capacity_hours_to_minutes
    assert capacity_hours_to_minutes(3) == 180
    assert capacity_hours_to_minutes(12) == 720
```

- [ ] **Step 2: Run the focused tests and verify the import fails.**

Run: `python -m pytest tests/test_planning_policy.py -v`

Expected: FAIL with `ModuleNotFoundError` or missing helper imports.

- [ ] **Step 3: Write failing tests for vacation windows and effective capacity.**

```python
def test_shortcut_vacation_is_inclusive_of_start_and_end():
    import datetime
    from backend.core.planning.policy import vacation_end_date, is_vacation_day
    start = datetime.date(2026, 7, 30)
    end = vacation_end_date(start, 3)
    assert end == datetime.date(2026, 8, 1)
    vacation = {"enabled": True, "start_date": start.isoformat(), "end_date": end.isoformat()}
    assert is_vacation_day(start, vacation)
    assert is_vacation_day(end, vacation)
    assert not is_vacation_day(datetime.date(2026, 8, 2), vacation)


def test_reduced_vacation_halves_capacity_without_going_below_three_hours():
    from backend.core.planning.policy import effective_capacity_minutes
    vacation = {"enabled": True, "strategy": "reduced"}
    assert effective_capacity_minutes(480, vacation) == 240
    assert effective_capacity_minutes(360, vacation) == 180


def test_diagnostic_only_vacation_has_zero_work_capacity():
    from backend.core.planning.policy import effective_capacity_minutes
    vacation = {"enabled": True, "strategy": "diagnostic_only"}
    assert effective_capacity_minutes(480, vacation) == 0
```

- [ ] **Step 4: Implement the pure policy module.**

Use ISO date strings in persisted dictionaries, treat malformed or missing vacation data as inactive, and make the reduced ratio default to `0.5`. Keep all calculations deterministic and free of `data_store` or NiceGUI imports.

- [ ] **Step 5: Run the focused policy tests.**

Run: `python -m pytest tests/test_planning_policy.py -v`

Expected: PASS.

- [ ] **Step 6: Commit the policy unit.**

```bash
git add backend/core/planning/policy.py tests/test_planning_policy.py
git commit -m "feat(planning): add capacity and vacation policy helpers"
```

### Task 2: Normalize persisted Planning preferences

**Files:**
- Modify: `backend/state/store.py:_get_default_preferences`
- Modify: `frontend/pages/planning_cockpit.py:_target_for` and preference accessors
- Test: `tests/test_planning_policy.py`

**Interfaces:**
- Consumes: existing `planning_targets` and new `planning_capacity_minutes` / `planning_vacation` preferences.
- Produces: one normalized capacity value in minutes and one normalized vacation dictionary for the cockpit.

- [ ] **Step 1: Add tests for legacy target migration.**

```python
def test_legacy_minute_target_can_be_read_as_capacity_hours():
    from backend.core.planning.policy import capacity_from_preferences
    prefs = {"planning_targets": {"2026-07-28": {"mode": "minutes", "value": 360}}}
    assert capacity_from_preferences(prefs, "2026-07-28") == 360


def test_invalid_or_missing_capacity_defaults_to_six_hours():
    from backend.core.planning.policy import capacity_from_preferences
    assert capacity_from_preferences({}, "2026-07-28") == 360
    assert capacity_from_preferences({"planning_capacity_minutes": 60}, "2026-07-28") == 180
```

- [ ] **Step 2: Run the tests and verify the new accessor is missing.**

Run: `python -m pytest tests/test_planning_policy.py -k "legacy or default" -v`

Expected: FAIL because `capacity_from_preferences` is not implemented.

- [ ] **Step 3: Implement preference normalization and defaults.**

Add defaults without removing existing preferences:

```python
"planning_capacity_minutes": 360,
"planning_vacation": {"enabled": False},
```

`capacity_from_preferences` must first use a valid `planning_capacity_minutes`; if absent, read a valid legacy daily target in minutes; otherwise return 360. It must clamp the result to 180–720 minutes.

- [ ] **Step 4: Run migration and existing planning tests.**

Run: `python -m pytest tests/test_planning_policy.py tests/test_todo_plan_du_jour.py -v`

Expected: PASS.

- [ ] **Step 5: Commit preference compatibility.**

```bash
git add backend/state/store.py frontend/pages/planning_cockpit.py backend/core/planning/policy.py tests/test_planning_policy.py
git commit -m "feat(planning): normalize personal capacity preferences"
```

### Task 3: Replace the capacity dialog with the validated Linear-style popover

**Files:**
- Modify: `frontend/pages/planning_cockpit.py:_open_capacity_dialog`, `_draw_topbar`, `_CSS`
- Test: `tests/test_planning_cockpit.py` (create if absent; use pure helpers for behavioral assertions)

**Interfaces:**
- Consumes: normalized capacity and vacation policy helpers from Task 1/2.
- Produces: a compact `Ma charge` action and popover that persists capacity and vacation choices, then refreshes the planning grid.

- [ ] **Step 1: Add pure tests for the shortcut date payloads used by the UI.**

```python
def test_shortcut_payload_for_one_three_and_five_days():
    import datetime
    from backend.core.planning.policy import vacation_payload
    start = datetime.date(2026, 7, 28)
    assert vacation_payload(start, 1, "reduced")["end_date"] == "2026-07-28"
    assert vacation_payload(start, 3, "reduced")["end_date"] == "2026-07-30"
    assert vacation_payload(start, 5, "diagnostic_only")["strategy"] == "diagnostic_only"
```

- [ ] **Step 2: Implement the payload helper and run its focused tests.**

Run: `python -m pytest tests/test_planning_policy.py -k shortcut -v`

Expected: PASS.

- [ ] **Step 3: Replace the current per-day minutes/items form.**

Render a single popover/card with:

```python
ui.label("Capacité quotidienne")
ui.toggle({3: "3 h", 6: "6 h", 9: "9 h", 12: "12 h"}, value=current_hours)
ui.number("Personnalisé (h)", min=3, max=12, step=1)
ui.switch("Mode vacances")
ui.toggle({"reduced": "Charge réduite", "diagnostic_only": "Coupure complète"})
ui.toggle({1: "1 jour", 3: "3 jours", 5: "5 jours"})
ui.button("Dates", on_click=open_date_picker)
```

Use a compact bordered button with `outline`, `dense`, and `no-caps` properties rather than the current flat icon button. Save capacity in `planning_capacity_minutes` and the vacation dictionary in `planning_vacation`; close the popover and schedule `_load_and_render()` after save. Keep explicit `Annuler` and `Enregistrer` actions.

- [ ] **Step 4: Remove the lower-card render path and center the grid.**

Delete the `bottom` element, `_draw_bottom`, and its invocation. Remove unused lower-card CSS. Keep `grid.style(... margin:0 auto)` and add a bounded wrapper width for 1- and 3-day views without changing the 7-column layout.

- [ ] **Step 5: Add active vacation status to the Planning subtitle.**

When active, append `· vacances jusqu’au <date> · charge réduite` or `· vacances jusqu’au <date> · diagnostic au retour`. Do not show an expired vacation as active.

- [ ] **Step 6: Run syntax and focused tests.**

Run: `python -m compileall frontend/pages/planning_cockpit.py backend/core/planning/policy.py -q` and `python -m pytest tests/test_planning_policy.py -v`.

Expected: compilation succeeds and all focused tests pass.

- [ ] **Step 7: Commit the UI redesign.**

```bash
git add frontend/pages/planning_cockpit.py backend/core/planning/policy.py tests/test_planning_policy.py
git commit -m "feat(planning): redesign capacity popover and remove lower cards"
```

### Task 4: Apply capacity and vacation policy to generated plans

**Files:**
- Modify: `frontend/pages/planning_cockpit.py:_load_and_render`
- Modify: `backend/core/planning/service.py:plan_day` only if needed to accept effective target values
- Test: `tests/test_planning_policy.py` and existing planning tests

**Interfaces:**
- Consumes: `capacity_from_preferences`, `is_vacation_day`, and `effective_capacity_minutes`.
- Produces: per-day `target_minutes` values that preserve urgency ordering and suppress ordinary slots during diagnostic-only vacation.

- [ ] **Step 1: Add tests for effective daily targets.**

```python
def test_daily_target_is_reduced_only_inside_vacation_window():
    import datetime
    from backend.core.planning.policy import target_for_day
    prefs = {
        "planning_capacity_minutes": 480,
        "planning_vacation": {
            "enabled": True,
            "start_date": "2026-07-30",
            "end_date": "2026-08-01",
            "strategy": "reduced",
        },
    }
    assert target_for_day(datetime.date(2026, 7, 29), prefs) == 480
    assert target_for_day(datetime.date(2026, 7, 30), prefs) == 240


def test_diagnostic_only_target_is_zero_inside_window():
    import datetime
    from backend.core.planning.policy import target_for_day
    prefs = {
        "planning_capacity_minutes": 480,
        "planning_vacation": {
            "enabled": True,
            "start_date": "2026-07-30",
            "end_date": "2026-08-01",
            "strategy": "diagnostic_only",
        },
    }
    assert target_for_day(datetime.date(2026, 7, 31), prefs) == 0
```

- [ ] **Step 2: Run the tests and verify the policy entry point is missing.**

Run: `python -m pytest tests/test_planning_policy.py -k target -v`

Expected: FAIL because `target_for_day` is not implemented.

- [ ] **Step 3: Implement `target_for_day` and wire it into `_load_and_render`.**

For every rendered day, compute the target once from current preferences. Pass it as `target_minutes`; never pass `target_items` from the new cockpit. For diagnostic-only vacation days, pass `target_minutes=0`, leaving source tasks untouched and letting the following day present the return state.

- [ ] **Step 4: Verify existing service behavior and targeted planning tests.**

Run: `python -m pytest tests/test_consolidation.py tests/test_todo_plan_du_jour.py tests/test_planning_policy.py -v`.

Expected: PASS.

- [ ] **Step 5: Commit plan integration.**

```bash
git add frontend/pages/planning_cockpit.py backend/core/planning/policy.py tests/test_planning_policy.py
git commit -m "feat(planning): apply capacity and vacation windows to plans"
```

### Task 5: Add the return diagnostic notice without mutating tasks

**Files:**
- Modify: `backend/core/planning/policy.py`
- Modify: `frontend/pages/planning_cockpit.py:_draw_topbar` or a focused notice renderer
- Test: `tests/test_planning_policy.py`

**Interfaces:**
- Consumes: all generated `ReviewTask` objects and an expired `diagnostic_only` vacation configuration.
- Produces: `return_diagnostic_tasks(tasks, vacation, today) -> list[ReviewTask]`, preserving original objects and selecting tasks whose due dates fall inside the vacation interval.

- [ ] **Step 1: Write failing tests for diagnostic selection.**

```python
def test_return_diagnostic_selects_tasks_expected_during_vacation():
    import datetime
    from types import SimpleNamespace
    from backend.core.planning.policy import return_diagnostic_tasks
    tasks = [
        SimpleNamespace(id="inside", due_date=datetime.date(2026, 7, 30)),
        SimpleNamespace(id="outside", due_date=datetime.date(2026, 8, 4)),
    ]
    vacation = {
        "enabled": True,
        "start_date": "2026-07-30",
        "end_date": "2026-08-01",
        "strategy": "diagnostic_only",
    }
    result = return_diagnostic_tasks(tasks, vacation, datetime.date(2026, 8, 2))
    assert [task.id for task in result] == ["inside"]
    assert tasks[0].due_date == datetime.date(2026, 7, 30)
```

- [ ] **Step 2: Run the test and verify it fails.**

Run: `python -m pytest tests/test_planning_policy.py -k diagnostic -v`

Expected: FAIL because `return_diagnostic_tasks` is not implemented.

- [ ] **Step 3: Implement diagnostic selection and expiry handling.**

Return an empty list unless strategy is `diagnostic_only`, the vacation is enabled, and `today > end_date`. Sort selected tasks by due date then existing priority score where available. Do not persist a new task and do not modify `due_date`.

- [ ] **Step 4: Render a compact return notice.**

When the current day is the first day after an expired diagnostic-only vacation and selected tasks exist, show an amber/indigo Linear-style notice near the Planning subtitle: `État des lieux après vacances` with the number of knowledge targets and an action linking to the existing review/QCM flow. If no selected tasks exist, render no notice.

- [ ] **Step 5: Run focused tests and compile.**

Run: `python -m pytest tests/test_planning_policy.py -v` and `python -m compileall frontend/pages/planning_cockpit.py backend/core/planning/policy.py -q`.

Expected: PASS and successful compilation.

- [ ] **Step 6: Commit the diagnostic behavior.**

```bash
git add frontend/pages/planning_cockpit.py backend/core/planning/policy.py tests/test_planning_policy.py
git commit -m "feat(planning): show return diagnostic after vacation"
```

### Task 6: End-to-end verification and visual QA

**Files:**
- Modify: `docs/PROGRESSION_SESSION_2026-07-28.md` only after verification, if the project convention requires a session note.

- [ ] **Step 1: Run the complete test suite.**

Run: `python -m pytest -q`.

Expected: all tests pass; report any pre-existing warnings without changing unrelated code.

- [ ] **Step 2: Run compilation and diff checks.**

Run: `python -m compileall backend frontend tests -q` and `git diff --check`.

Expected: compilation succeeds. Any unrelated pre-existing whitespace failures are recorded, not reformatted opportunistically.

- [ ] **Step 3: Manually verify the Planning cockpit.**

Start the app, open `/planning`, and check at 1j, 3j, and 7j:

1. The grid is centered and no lower cards are present.
2. `Ma charge` matches the compact Linear-style button.
3. 3/6/9/12 h and custom capacity save and reload correctly.
4. 1/3/5-day vacation shortcuts show the right inclusive dates.
5. Reduced mode halves capacity; complete mode shows no ordinary slots.
6. Expired diagnostic-only vacation shows the return notice without changing source task dates.

- [ ] **Step 4: Commit only the session note if needed.**

```bash
git status --short
git add docs/PROGRESSION_SESSION_2026-07-28.md
git commit -m "docs: record planning capacity vacation verification"
```

Do not commit generated browser companion content.
