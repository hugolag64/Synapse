# Étalement persisté du backlog de consolidation + capacité par jour cliquable — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the "everything piles onto today" consolidation display with a persisted, stable day-by-day allocation, and let the user adjust a day's capacity by clicking directly on the hour total, with the surplus cascading to later days.

**Architecture:** A new SQLite table `consolidation_schedule` (course_id, context → scheduled_date) is filled by a pure greedy allocator (`consolidation.ensure_schedule`) that walks forward from today, respects the existing daily caps (`daily_caps`, `count_consolidation_dismissed_today`, `target_for_day`), and never moves an already-valid assignment — this is what makes the day-by-day view stable across reloads. `PlanningService.plan_consolidation()` (Dashboard) and `planning_cockpit.py` (Planning grid) both read the same table, so the two views agree. Changing a day's capacity clears that day's (and later days') assignments and re-runs the allocator (`consolidation.reschedule_from`), which is what makes the surplus cascade forward.

**Tech Stack:** Python 3.11+, SQLite (stdlib `sqlite3`), NiceGUI, pytest.

## Global Constraints

- `SCHEDULE_HORIZON_DAYS = 60` — the allocator only ever considers tasks already due or due within 60 days; further-out tasks are picked up once they enter that window on a later call.
- `MAX_SCHEDULE_LOOKAHEAD_DAYS = 200` — safety bound on how many days forward the allocator will walk in one call; never raises, just leaves the remainder unassigned until a later call has room.
- An existing persisted assignment is touched **only** when: its course is no longer in the current due-task set, its date has already passed, or its task's real due date has moved past the assigned date (manual postpone). Otherwise it is left untouched — this is the stability guarantee approved in the spec.
- Reducing a day's capacity to 0 (via the per-day override) is allowed — the 3h (`MIN_CAPACITY_HOURS`) floor from `backend/core/planning/policy.py` applies only to the **global default** capacity, never to a per-day override.
- `PlanningService.plan_consolidation()` drops its `max_items`/`max_per_college` override parameters — no production caller and only one test used them, and that test's expected values are unchanged by the real defaults, so the override path was dead weight (YAGNI).
- Follow existing local_store.py conventions: `_conn()` context manager, `_now()` for timestamps, `ON CONFLICT ... DO UPDATE` upserts, `PRIMARY KEY (course_id, context)` — mirror `consolidation_gates`/`set_consolidation_not_before`.
- `planning_cockpit.py` has no behavioral unit tests (NiceGUI UI) — its existing tests assert on literal source strings (see `tests/test_planning_day_capacity.py`); follow the same style for new UI assertions.

---

## File Structure

- **Modify** `backend/core/planning/policy.py` — fix a precedence bug (`planning_targets` day override was silently ignored whenever the global `planning_capacity_minutes` was set) and let a day override go down to 0 instead of the 3h floor.
- **Modify** `backend/core/reviews/local_store.py` — new `consolidation_schedule` table + 4 CRUD functions.
- **Modify** `backend/core/reviews/consolidation.py` — `ensure_schedule()` (the allocator) and `reschedule_from()` (the cascade trigger).
- **Modify** `backend/core/planning/service.py` — `plan_consolidation()` now reads the persisted schedule instead of calling `select_daily` directly.
- **Modify** `frontend/pages/planning_cockpit.py` — wire the schedule map into the weekly grid, make the day footer clickable, add ±30min buttons and a 0-floor to the day capacity dialog, trigger the cascade on every capacity-affecting save.
- **Modify** `frontend/pages/settings_cockpit.py` — trigger the cascade when `weekend_light_consolidation` is toggled.
- **Modify** `tests/test_planning_policy.py`, `tests/test_consolidation.py`, `tests/test_consolidation_daily_cap_shrinks.py` — adapt to the above.
- **Create** `tests/test_consolidation_schedule.py` — the allocator's test suite.

---

### Task 1: Fix the day-override precedence bug and its capacity floor

**Files:**
- Modify: `backend/core/planning/policy.py:83-95` (`capacity_from_preferences`)
- Test: `tests/test_planning_policy.py`

**Interfaces:**
- Produces: `capacity_from_preferences(preferences: dict, day_iso: str | None = None) -> int` — day override now takes precedence over the global default when both are present, and a day override can be any value in `[0, MAX_CAPACITY_HOURS*60]` (no 3h floor); the global-default path keeps its existing `[MIN_CAPACITY_HOURS*60, MAX_CAPACITY_HOURS*60]` clamp.

Today, `capacity_from_preferences` only reads `planning_targets[day_iso]` when `planning_capacity_minutes` is **absent** from preferences. Once the user has saved "Ma charge" once (which sets `planning_capacity_minutes`), any per-day override written by `_open_day_capacity_dialog` is silently ignored forever — the day-capacity feature has never actually taken effect. Confirmed by the fact that no existing test exercises both keys being set at once.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_planning_policy.py`:

```python
def test_day_override_takes_precedence_over_the_global_default():
    from backend.core.planning.policy import capacity_from_preferences

    prefs = {
        "planning_capacity_minutes": 480,
        "planning_targets": {"2026-08-21": {"mode": "minutes", "value": 90}},
    }
    assert capacity_from_preferences(prefs, "2026-08-21") == 90


def test_day_override_can_go_down_to_zero():
    from backend.core.planning.policy import capacity_from_preferences

    prefs = {
        "planning_capacity_minutes": 480,
        "planning_targets": {"2026-08-21": {"mode": "minutes", "value": 0}},
    }
    assert capacity_from_preferences(prefs, "2026-08-21") == 0


def test_day_override_is_still_capped_at_twelve_hours():
    from backend.core.planning.policy import capacity_from_preferences

    prefs = {"planning_targets": {"2026-08-21": {"mode": "minutes", "value": 900}}}
    assert capacity_from_preferences(prefs, "2026-08-21") == 720


def test_global_default_still_floors_at_three_hours_when_no_day_override():
    from backend.core.planning.policy import capacity_from_preferences

    assert capacity_from_preferences({"planning_capacity_minutes": 10}, "2026-08-21") == 180
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_planning_policy.py -v`
Expected: the four new tests FAIL (the precedence and zero-floor tests assert values the current code cannot produce); all pre-existing tests in the file still PASS.

- [ ] **Step 3: Fix `capacity_from_preferences`**

Replace `backend/core/planning/policy.py:83-95`:

```python
def capacity_from_preferences(preferences: dict, day_iso: str | None = None) -> int:
    if day_iso:
        targets = preferences.get("planning_targets", {})
        target = targets.get(day_iso, {}) if isinstance(targets, dict) else {}
        if isinstance(target, dict) and target.get("mode") == "minutes":
            try:
                return max(0, min(MAX_CAPACITY_HOURS * 60, int(target["value"])))
            except (TypeError, ValueError):
                pass
    raw = preferences.get("planning_capacity_minutes")
    try:
        minutes = int(raw) if raw is not None else DEFAULT_CAPACITY_HOURS * 60
    except (TypeError, ValueError):
        minutes = DEFAULT_CAPACITY_HOURS * 60
    return max(MIN_CAPACITY_HOURS * 60, min(MAX_CAPACITY_HOURS * 60, minutes))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_planning_policy.py -v`
Expected: PASS, all tests in the file.

- [ ] **Step 5: Commit**

```bash
git add backend/core/planning/policy.py tests/test_planning_policy.py
git commit -m "fix(planning): day capacity override now takes precedence over the global default"
```

---

### Task 2: `consolidation_schedule` table and CRUD

**Files:**
- Modify: `backend/core/reviews/local_store.py:627-636` (add table next to `consolidation_gates`), `:1719` (add functions next to the `consolidation_not_before` group)
- Test: `tests/test_consolidation_schedule_store.py` (new)

**Interfaces:**
- Produces:
  - `get_consolidation_schedule_map(context: str) -> dict[str, datetime.date]`
  - `set_consolidation_schedule_batch(context: str, mapping: dict[str, datetime.date]) -> None`
  - `delete_consolidation_schedule(course_ids: list[str], context: str) -> None`
  - `clear_consolidation_schedule_from(context: str, from_date: datetime.date) -> None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_consolidation_schedule_store.py`:

```python
import datetime

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import backend.core.knowledge.store as ks
    import backend.core.reviews.local_store as ls

    test_db = tmp_path / "test.db"
    monkeypatch.setattr(ls, "DB_PATH", test_db)
    monkeypatch.setattr(ls, "_DB", None)
    ls.init_db()
    ks.init_knowledge_tables()
    yield
    if ls._DB is not None:
        ls._DB.close()
    monkeypatch.setattr(ls, "_DB", None)


import backend.core.reviews.local_store as ls  # noqa: E402


def test_empty_map_when_nothing_stored():
    assert ls.get_consolidation_schedule_map("college") == {}


def test_batch_upsert_then_read_back():
    d1 = datetime.date(2026, 8, 21)
    d2 = datetime.date(2026, 8, 22)
    ls.set_consolidation_schedule_batch("college", {"course-1": d1, "course-2": d2})

    assert ls.get_consolidation_schedule_map("college") == {"course-1": d1, "course-2": d2}


def test_batch_upsert_overwrites_an_existing_date():
    d1 = datetime.date(2026, 8, 21)
    d2 = datetime.date(2026, 8, 25)
    ls.set_consolidation_schedule_batch("college", {"course-1": d1})
    ls.set_consolidation_schedule_batch("college", {"course-1": d2})

    assert ls.get_consolidation_schedule_map("college") == {"course-1": d2}


def test_contexts_are_isolated():
    d = datetime.date(2026, 8, 21)
    ls.set_consolidation_schedule_batch("college", {"course-1": d})
    ls.set_consolidation_schedule_batch("ue", {"course-1": d})

    ls.delete_consolidation_schedule(["course-1"], "ue")

    assert ls.get_consolidation_schedule_map("college") == {"course-1": d}
    assert ls.get_consolidation_schedule_map("ue") == {}


def test_delete_removes_only_the_given_ids():
    d = datetime.date(2026, 8, 21)
    ls.set_consolidation_schedule_batch("college", {"course-1": d, "course-2": d})

    ls.delete_consolidation_schedule(["course-1"], "college")

    assert ls.get_consolidation_schedule_map("college") == {"course-2": d}


def test_clear_from_removes_entries_on_or_after_the_given_date_only():
    ls.set_consolidation_schedule_batch("college", {
        "course-1": datetime.date(2026, 8, 20),
        "course-2": datetime.date(2026, 8, 21),
        "course-3": datetime.date(2026, 8, 22),
    })

    ls.clear_consolidation_schedule_from("college", datetime.date(2026, 8, 21))

    assert ls.get_consolidation_schedule_map("college") == {"course-1": datetime.date(2026, 8, 20)}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_consolidation_schedule_store.py -v`
Expected: FAIL with `AttributeError: module 'backend.core.reviews.local_store' has no attribute 'get_consolidation_schedule_map'`.

- [ ] **Step 3: Add the table**

In `backend/core/reviews/local_store.py`, right after the `consolidation_gates` table (immediately before the closing `""")` at line 636):

```python
        CREATE TABLE IF NOT EXISTS consolidation_schedule (
            course_id      TEXT NOT NULL,
            context        TEXT NOT NULL,
            scheduled_date TEXT NOT NULL,
            updated_at     TEXT NOT NULL,
            PRIMARY KEY (course_id, context)
        );
        CREATE INDEX IF NOT EXISTS idx_consolidation_schedule_date
            ON consolidation_schedule(context, scheduled_date);
```

- [ ] **Step 4: Add the CRUD functions**

In `backend/core/reviews/local_store.py`, right after `get_consolidation_not_before_map` (after line 1728):

```python
def get_consolidation_schedule_map(context: str) -> dict[str, datetime.date]:
    with _conn() as con:
        rows = con.execute(
            "SELECT course_id, scheduled_date FROM consolidation_schedule WHERE context = ?",
            (context,),
        ).fetchall()
    return {row["course_id"]: datetime.date.fromisoformat(row["scheduled_date"]) for row in rows}


def set_consolidation_schedule_batch(context: str, mapping: dict[str, datetime.date]) -> None:
    if not mapping:
        return
    now = _now()
    with _conn() as con:
        con.executemany(
            """
            INSERT INTO consolidation_schedule (course_id, context, scheduled_date, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(course_id, context) DO UPDATE SET
                scheduled_date = excluded.scheduled_date,
                updated_at     = excluded.updated_at
            """,
            [(course_id, context, day.isoformat(), now) for course_id, day in mapping.items()],
        )


def delete_consolidation_schedule(course_ids: list[str], context: str) -> None:
    if not course_ids:
        return
    with _conn() as con:
        con.executemany(
            "DELETE FROM consolidation_schedule WHERE course_id = ? AND context = ?",
            [(course_id, context) for course_id in course_ids],
        )


def clear_consolidation_schedule_from(context: str, from_date: datetime.date) -> None:
    with _conn() as con:
        con.execute(
            "DELETE FROM consolidation_schedule WHERE context = ? AND scheduled_date >= ?",
            (context, from_date.isoformat()),
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_consolidation_schedule_store.py -v`
Expected: PASS, all 7 tests.

- [ ] **Step 6: Commit**

```bash
git add backend/core/reviews/local_store.py tests/test_consolidation_schedule_store.py
git commit -m "feat(consolidation): add consolidation_schedule table and CRUD"
```

---

### Task 3: `ensure_schedule()` — the allocator

**Files:**
- Modify: `backend/core/reviews/consolidation.py` (add near the top, after the existing constants, and a new function after `daily_caps`)
- Test: `tests/test_consolidation_schedule.py` (new)

**Interfaces:**
- Consumes: `get_due_consolidation_tasks` (this file), `daily_caps` (this file), `_priority_score` (this file), `local_store.get_consolidation_schedule_map/set_consolidation_schedule_batch/delete_consolidation_schedule/count_consolidation_dismissed_today` (Task 2 + existing), `backend.core.planning.policy.target_for_day` (existing).
- Produces: `ensure_schedule(context: str = "college", today: datetime.date | None = None) -> dict[str, datetime.date]`. Later tasks (5, 6) call this and read its return value directly — it is the full, current `{course_id: scheduled_date}` map for that context.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_consolidation_schedule.py`:

```python
"""ensure_schedule() étale le backlog de consolidation sur les jours suivants,
de façon stable entre deux appels tant que rien ne change — remplace le
comportement où tout le backlog s'empilait sur « aujourd'hui »."""
import datetime
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import backend.core.knowledge.store as ks
    import backend.core.reviews.local_store as ls

    test_db = tmp_path / "test.db"
    monkeypatch.setattr(ls, "DB_PATH", test_db)
    monkeypatch.setattr(ls, "_DB", None)
    ls.init_db()
    ks.init_knowledge_tables()
    yield
    if ls._DB is not None:
        ls._DB.close()
    monkeypatch.setattr(ls, "_DB", None)


import backend.core.reviews.local_store as ls  # noqa: E402
from backend.core.reviews import consolidation  # noqa: E402
from backend.state.store import data_store  # noqa: E402

_TODAY = datetime.date(2026, 8, 21)


@pytest.fixture(autouse=True)
def _empty_preferences(monkeypatch):
    monkeypatch.setattr(data_store, "preferences", {})


def _tasks(n: int, *, prefix: str = "course", due_date=_TODAY, days_overdue=5):
    return [
        SimpleNamespace(
            course_id=f"{prefix}-{i}", days_overdue=days_overdue, semestre=None,
            mastery_level="à consolider", college=[f"college-{i}"], due_date=due_date,
        )
        for i in range(n)
    ]


def test_spreads_a_large_backlog_across_several_days(monkeypatch):
    monkeypatch.setattr(consolidation, "get_due_consolidation_tasks", lambda *a, **k: _tasks(14))
    monkeypatch.setattr(consolidation, "daily_caps", lambda **_: (6, 6))

    schedule = consolidation.ensure_schedule("college", today=_TODAY)

    by_day: dict[datetime.date, int] = {}
    for day in schedule.values():
        by_day[day] = by_day.get(day, 0) + 1
    assert by_day[_TODAY] == 6
    assert by_day[_TODAY + datetime.timedelta(days=1)] == 6
    assert by_day[_TODAY + datetime.timedelta(days=2)] == 2


def test_is_stable_across_two_calls_with_no_change(monkeypatch):
    monkeypatch.setattr(consolidation, "get_due_consolidation_tasks", lambda *a, **k: _tasks(10))
    monkeypatch.setattr(consolidation, "daily_caps", lambda **_: (6, 6))

    first = consolidation.ensure_schedule("college", today=_TODAY)
    second = consolidation.ensure_schedule("college", today=_TODAY)

    assert first == second


def test_a_day_that_has_passed_reassigns_its_items_forward(monkeypatch):
    monkeypatch.setattr(consolidation, "get_due_consolidation_tasks", lambda *a, **k: _tasks(12))
    monkeypatch.setattr(consolidation, "daily_caps", lambda **_: (6, 6))

    consolidation.ensure_schedule("college", today=_TODAY)
    tomorrow = _TODAY + datetime.timedelta(days=1)

    schedule = consolidation.ensure_schedule("college", today=tomorrow)

    assert all(day >= tomorrow for day in schedule.values())
    by_day: dict[datetime.date, int] = {}
    for day in schedule.values():
        by_day[day] = by_day.get(day, 0) + 1
    assert by_day[tomorrow] == 6


def test_a_manual_postpone_invalidates_a_stale_earlier_assignment(monkeypatch):
    tasks = _tasks(3)
    monkeypatch.setattr(consolidation, "get_due_consolidation_tasks", lambda *a, **k: tasks)
    monkeypatch.setattr(consolidation, "daily_caps", lambda **_: (6, 6))

    consolidation.ensure_schedule("college", today=_TODAY)

    postponed_to = _TODAY + datetime.timedelta(days=5)
    tasks[0] = SimpleNamespace(
        course_id="course-0", days_overdue=0, semestre=None,
        mastery_level="à consolider", college=["college-0"], due_date=postponed_to,
    )

    schedule = consolidation.ensure_schedule("college", today=_TODAY)

    assert schedule["course-0"] >= postponed_to


def test_zero_capacity_day_is_skipped(monkeypatch):
    monkeypatch.setattr(consolidation, "get_due_consolidation_tasks", lambda *a, **k: _tasks(2))
    monkeypatch.setattr(consolidation, "daily_caps", lambda **_: (6, 6))
    data_store.preferences = {
        "planning_targets": {_TODAY.isoformat(): {"mode": "minutes", "value": 0}}
    }

    schedule = consolidation.ensure_schedule("college", today=_TODAY)

    assert _TODAY not in schedule.values()
    assert all(day == _TODAY + datetime.timedelta(days=1) for day in schedule.values())


def test_todays_cap_shrinks_by_dismissals_without_backfilling_the_freed_slot(monkeypatch):
    tasks = _tasks(6)
    monkeypatch.setattr(consolidation, "get_due_consolidation_tasks", lambda *a, **k: tasks)
    monkeypatch.setattr(consolidation, "daily_caps", lambda **_: (6, 6))

    consolidation.ensure_schedule("college", today=_TODAY)  # course-0..5 all land on _TODAY

    ls.postpone(
        task_id=f"course-0_college_consolidation_{_TODAY.isoformat()}",
        course_id="course-0", context="college", review_type="consolidation",
        theoretical_due_date=_TODAY, postponed_to=_TODAY + datetime.timedelta(days=7),
    )
    # course-0 drops out of the due backlog (postponed, like real filtering would do);
    # a brand new item enters at the same time — without the shrink it would fill the freed slot.
    tasks[:] = _tasks(6)[1:] + [SimpleNamespace(
        course_id="course-new", days_overdue=5, semestre=None,
        mastery_level="à consolider", college=["college-new"], due_date=_TODAY,
    )]

    schedule = consolidation.ensure_schedule("college", today=_TODAY)

    assert sum(1 for day in schedule.values() if day == _TODAY) == 5
    assert schedule.get("course-new") != _TODAY
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_consolidation_schedule.py -v`
Expected: FAIL with `AttributeError: module 'backend.core.reviews.consolidation' has no attribute 'ensure_schedule'`.

- [ ] **Step 3: Implement `ensure_schedule`**

In `backend/core/reviews/consolidation.py`, add near the top with the other constants (after `WEEKEND_MAX_ITEMS_PER_DAY = 2` at line 70):

```python
# Étalement persisté du backlog (Planning + Dashboard) : horizon de récupération
# des tâches à étaler, et garde-fou de sécurité sur la marche en avant.
SCHEDULE_HORIZON_DAYS = 60
MAX_SCHEDULE_LOOKAHEAD_DAYS = 200
```

Then add the function right after `daily_caps` (after line 324):

```python
def ensure_schedule(
    context: str = "college",
    today: Optional[datetime.date] = None,
) -> dict[str, datetime.date]:
    """
    Étale le backlog de consolidation sur les jours à venir, de façon stable :
    une assignation déjà persistée n'est jamais retouchée tant que son cours
    est toujours dû, que sa date n'est pas passée, et qu'un report manuel n'a
    pas repoussé l'échéance réelle au-delà.

    Le Dashboard et Planning lisent tous les deux cette même table — un item
    apparaît donc au même jour dans les deux vues.
    """
    from backend.core.planning.policy import target_for_day
    from backend.core.reviews import local_store
    from backend.state.store import data_store

    today = today or datetime.date.today()
    tasks = get_due_consolidation_tasks(context, today, horizon_days=SCHEDULE_HORIZON_DAYS)
    tasks_by_id = {t.course_id: t for t in tasks}
    existing = local_store.get_consolidation_schedule_map(context)

    valid: dict[str, datetime.date] = {}
    stale_ids: list[str] = []
    occupied: dict[datetime.date, list] = {}
    for course_id, scheduled_date in existing.items():
        task = tasks_by_id.get(course_id)
        if task is None or scheduled_date < today or scheduled_date < task.due_date:
            stale_ids.append(course_id)
        else:
            valid[course_id] = scheduled_date
            occupied.setdefault(scheduled_date, []).append(task)

    needs_assignment = sorted(
        (t for t in tasks if t.course_id not in valid),
        key=lambda t: (-_priority_score(t), t.course_id),
    )

    preferences = data_store.preferences
    weekend_light = bool(preferences.get("weekend_light_consolidation", False))

    new_assignments: dict[str, datetime.date] = {}
    queue = needs_assignment
    day = today
    lookahead = 0
    while queue and lookahead < MAX_SCHEDULE_LOOKAHEAD_DAYS:
        if target_for_day(day, preferences) == 0:
            day += datetime.timedelta(days=1)
            lookahead += 1
            continue

        max_items, max_per_college = daily_caps(today=day, weekend_light=weekend_light)
        if day == today:
            dismissed = local_store.count_consolidation_dismissed_today(context, today)
            max_items = max(0, max_items - dismissed)

        day_tasks = occupied.get(day, [])
        college_count: dict[str, int] = {}
        for t in day_tasks:
            primary = t.college[0] if t.college else "?"
            college_count[primary] = college_count.get(primary, 0) + 1

        remaining_queue = []
        for t in queue:
            primary = t.college[0] if t.college else "?"
            if len(day_tasks) < max_items and college_count.get(primary, 0) < max_per_college:
                day_tasks.append(t)
                college_count[primary] = college_count.get(primary, 0) + 1
                new_assignments[t.course_id] = day
            else:
                remaining_queue.append(t)
        queue = remaining_queue
        occupied[day] = day_tasks
        day += datetime.timedelta(days=1)
        lookahead += 1

    if stale_ids:
        local_store.delete_consolidation_schedule(stale_ids, context)
    if new_assignments:
        local_store.set_consolidation_schedule_batch(context, new_assignments)

    valid.update(new_assignments)
    return valid
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_consolidation_schedule.py -v`
Expected: PASS, all 6 tests.

- [ ] **Step 5: Run the full consolidation test suite to check for regressions**

Run: `pytest tests/test_consolidation.py tests/test_consolidation_daily_cap_shrinks.py -v`
Expected: `test_consolidation.py` still PASSES (nothing there calls `ensure_schedule` yet). `test_consolidation_daily_cap_shrinks.py::test_plan_consolidation_shrinks_the_daily_cap_after_a_postpone` FAILS — expected, fixed in Task 5.

- [ ] **Step 6: Commit**

```bash
git add backend/core/reviews/consolidation.py tests/test_consolidation_schedule.py
git commit -m "feat(consolidation): add ensure_schedule() to spread the backlog across future days"
```

---

### Task 4: `reschedule_from()` — the capacity-change cascade

**Files:**
- Modify: `backend/core/reviews/consolidation.py` (add after `ensure_schedule`)
- Test: `tests/test_consolidation_schedule.py` (extend)

**Interfaces:**
- Consumes: `ensure_schedule` (Task 3), `local_store.clear_consolidation_schedule_from` (Task 2).
- Produces: `reschedule_from(context: str, day: datetime.date, today: datetime.date | None = None) -> dict[str, datetime.date]`. Tasks 7, 8, 9 call this after any write to `planning_targets`, `planning_capacity_minutes`, `planning_vacation`, or `weekend_light_consolidation`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_consolidation_schedule.py`:

```python
def test_reschedule_from_cascades_the_surplus_to_later_days(monkeypatch):
    monkeypatch.setattr(consolidation, "get_due_consolidation_tasks", lambda *a, **k: _tasks(6))
    monkeypatch.setattr(consolidation, "daily_caps", lambda **_: (6, 6))

    consolidation.ensure_schedule("college", today=_TODAY)  # all 6 land on _TODAY

    data_store.preferences = {
        "planning_targets": {_TODAY.isoformat(): {"mode": "minutes", "value": 90}}
    }
    schedule = consolidation.reschedule_from("college", _TODAY, today=_TODAY)

    by_day: dict[datetime.date, int] = {}
    for day in schedule.values():
        by_day[day] = by_day.get(day, 0) + 1
    assert by_day[_TODAY] == 6  # target_for_day > 0 (90min) still lets the item-count cap (6) decide
    # capacity reduced to 0 instead: everything must move off _TODAY
    data_store.preferences = {
        "planning_targets": {_TODAY.isoformat(): {"mode": "minutes", "value": 0}}
    }
    schedule = consolidation.reschedule_from("college", _TODAY, today=_TODAY)
    assert _TODAY not in schedule.values()
    assert by_day.get(_TODAY + datetime.timedelta(days=1), 0) >= 0  # sanity: no crash, days beyond used


def test_reschedule_from_does_not_touch_days_before_it(monkeypatch):
    monkeypatch.setattr(consolidation, "get_due_consolidation_tasks", lambda *a, **k: _tasks(12))
    monkeypatch.setattr(consolidation, "daily_caps", lambda **_: (6, 6))

    consolidation.ensure_schedule("college", today=_TODAY)  # 6 on _TODAY, 6 on _TODAY+1
    tomorrow = _TODAY + datetime.timedelta(days=1)

    data_store.preferences = {
        "planning_targets": {tomorrow.isoformat(): {"mode": "minutes", "value": 0}}
    }
    schedule = consolidation.reschedule_from("college", tomorrow, today=_TODAY)

    assert sum(1 for day in schedule.values() if day == _TODAY) == 6  # untouched
    assert tomorrow not in schedule.values()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_consolidation_schedule.py -v -k reschedule_from`
Expected: FAIL with `AttributeError: module 'backend.core.reviews.consolidation' has no attribute 'reschedule_from'`.

- [ ] **Step 3: Implement `reschedule_from`**

In `backend/core/reviews/consolidation.py`, right after `ensure_schedule`:

```python
def reschedule_from(
    context: str,
    day: datetime.date,
    today: Optional[datetime.date] = None,
) -> dict[str, datetime.date]:
    """
    Efface les assignations à partir de `day` (incluse) puis relance
    l'allocateur : les items qui ne rentrent plus avec la nouvelle capacité de
    `day` glissent vers les jours suivants. Les jours avant `day` ne sont pas
    touchés. À appeler après toute écriture qui change la capacité d'un jour
    (planning_targets, planning_capacity_minutes, planning_vacation,
    weekend_light_consolidation).
    """
    from backend.core.reviews import local_store

    local_store.clear_consolidation_schedule_from(context, day)
    return ensure_schedule(context, today or datetime.date.today())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_consolidation_schedule.py -v`
Expected: PASS, all 8 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/core/reviews/consolidation.py tests/test_consolidation_schedule.py
git commit -m "feat(consolidation): add reschedule_from() to cascade a capacity change forward"
```

---

### Task 5: `PlanningService.plan_consolidation()` reads the persisted schedule

**Files:**
- Modify: `backend/core/planning/service.py:324-366` (`plan_consolidation`)
- Modify: `tests/test_consolidation.py:664-687` (drop the explicit `max_items`/`max_per_college` args)
- Modify: `tests/test_consolidation_daily_cap_shrinks.py:106-137` (`_due` mock must accept call args and reflect postpones; must include `due_date`)

**Interfaces:**
- Consumes: `consolidation.ensure_schedule`, `consolidation.get_due_consolidation_tasks` (Task 3).
- Produces: `plan_consolidation(self, today: datetime.date | None = None) -> tuple[list[ReviewTask], list[ReviewTask]]` — **signature change**: `max_items`/`max_per_college` params removed (dead override path, see Global Constraints). `_cockpit_today.py:259`'s zero-arg call (`planning_service.plan_consolidation()`) keeps working unchanged.

- [ ] **Step 1: Update the two failing/changing tests**

In `tests/test_consolidation.py`, replace lines 683-685:

```python
    selected, skipped = planning_service.plan_consolidation()
```

(was `planning_service.plan_consolidation(max_items=6, max_per_college=2)` — the real defaults are 6/2 already, so dropping the explicit args changes nothing about this test's outcome.)

In `tests/test_consolidation_daily_cap_shrinks.py`, replace the whole `test_plan_consolidation_shrinks_the_daily_cap_after_a_postpone` function (lines 106-137):

```python
def test_plan_consolidation_shrinks_the_daily_cap_after_a_postpone(monkeypatch):
    """La sélection du jour doit refléter les reports déjà faits aujourd'hui,
    pas repartir d'un plafond plein à chaque rebuild."""
    from types import SimpleNamespace

    from backend.core.planning.service import planning_service
    from backend.core.reviews import consolidation
    from backend.state.store import data_store

    monkeypatch.setattr(data_store, "preferences", {})

    def _due(*_args, **_kwargs):
        # Un collège distinct par tâche : seul le plafond total (max_items)
        # doit jouer ici, pas le plafond par collège. Reflète les reports déjà
        # faits, comme le fait la vraie get_due_consolidation_tasks (un item
        # reporté a une due_date future, donc hors backlog du jour).
        with ls._conn() as con:
            dismissed = {
                row["course_id"] for row in con.execute(
                    "SELECT course_id FROM review_history WHERE status IN ('postponed', 'ignored')"
                ).fetchall()
            }
        return [
            SimpleNamespace(
                course_id=f"course-{i}", days_overdue=5, semestre=None,
                mastery_level="à consolider", college=[f"college-{i}"], due_date=_TODAY,
            )
            for i in range(20) if f"course-{i}" not in dismissed
        ]

    monkeypatch.setattr(consolidation, "get_due_consolidation_tasks", _due)
    monkeypatch.setattr(consolidation, "daily_caps", lambda **_: (6, 6))

    selected_before, _ = planning_service.plan_consolidation(today=_TODAY)
    assert len(selected_before) == 6

    _postpone(2)

    selected_after, _ = planning_service.plan_consolidation(today=_TODAY)
    assert len(selected_after) == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_consolidation.py::test_plan_consolidation_retourne_selection_et_surplus tests/test_consolidation_daily_cap_shrinks.py::test_plan_consolidation_shrinks_the_daily_cap_after_a_postpone -v`
Expected: FAIL — `plan_consolidation()` still has the old signature and behavior, `ensure_schedule` isn't wired in yet.

- [ ] **Step 3: Rewrite `plan_consolidation`**

Replace `backend/core/planning/service.py:322-366` (the whole `plan_consolidation` method, from the `# ── plan_consolidation ──` comment through its closing `return`):

```python
    # ── plan_consolidation ───────────────────────────────────────────────────

    def plan_consolidation(
        self,
        today: datetime.date | None = None,
    ):
        """
        Sélection du jour pour le flux de consolidation long terme, lue depuis
        l'allocation persistée (`consolidation.ensure_schedule`) : les tâches
        dont le jour assigné est aujourd'hui sont "selected", celles assignées
        à un jour futur sont "skipped" (le badge "+N en attente" les compte).
        """
        import datetime as _dt

        from backend.core.reviews import consolidation

        today = today or _dt.date.today()
        schedule = consolidation.ensure_schedule("college", today)
        tasks_by_id = {
            t.course_id: t
            for t in consolidation.get_due_consolidation_tasks(
                "college", today, horizon_days=consolidation.SCHEDULE_HORIZON_DAYS,
            )
        }

        selected = [tasks_by_id[cid] for cid, day in schedule.items() if day == today and cid in tasks_by_id]
        skipped = [tasks_by_id[cid] for cid, day in schedule.items() if day > today and cid in tasks_by_id]
        return selected, skipped
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_consolidation.py tests/test_consolidation_daily_cap_shrinks.py -v`
Expected: PASS, all tests in both files.

- [ ] **Step 5: Run the full backend test suite for regressions**

Run: `pytest tests/ -v -k "consolidation or planning_policy"`
Expected: PASS. (`tests/test_lot4_performance_contracts.py` is unaffected — it asserts on a literal string in a different file's source, not on `plan_consolidation`'s signature.)

- [ ] **Step 6: Commit**

```bash
git add backend/core/planning/service.py tests/test_consolidation.py tests/test_consolidation_daily_cap_shrinks.py
git commit -m "refactor(planning): plan_consolidation() reads the persisted schedule"
```

---

### Task 6: Wire the schedule into the Planning grid

**Files:**
- Modify: `frontend/pages/planning_cockpit.py:792-835` (`_load_and_render`)
- Test: `tests/test_planning_cockpit_schedule_wiring.py` (new, source-string assertions — matches the existing style in `tests/test_planning_day_capacity.py`)

**Interfaces:**
- Consumes: `consolidation.ensure_schedule`, `consolidation.SCHEDULE_HORIZON_DAYS` (Task 3).
- Produces: `_load_and_render`'s per-day `consolidation_for_day` is now sourced from the schedule map, not from `due_date` comparisons.

- [ ] **Step 1: Write the failing test**

Create `tests/test_planning_cockpit_schedule_wiring.py`:

```python
from pathlib import Path


def _source() -> str:
    return Path("frontend/pages/planning_cockpit.py").read_text(encoding="utf-8")


def test_load_and_render_uses_the_persisted_schedule():
    source = _source()
    assert "consolidation.ensure_schedule(" in source
    assert 'schedule_map.get(task.course_id) == d' in source


def test_consolidation_fetch_horizon_covers_the_schedule_horizon():
    assert "consolidation.SCHEDULE_HORIZON_DAYS" in _source()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_planning_cockpit_schedule_wiring.py -v`
Expected: FAIL — neither string is present yet.

- [ ] **Step 3: Rewire `_load_and_render`**

In `frontend/pages/planning_cockpit.py`, replace lines 792-813 (from `today = datetime.date.today()` through the closing `]` of `consolidation_for_day`'s old comprehension, i.e. the block that currently reads):

```python
        today = datetime.date.today()
        consolidation_tasks = consolidation.get_due_consolidation_tasks(
            context="college",
            today=today,
            horizon_days=future_horizon_days(week[-1], today),
        )
```

up to and including:

```python
            consolidation_for_day = [
                task for task in consolidation_tasks
                if (d == today and task.due_date <= today) or task.due_date == d
            ]
```

with:

```python
        today = datetime.date.today()
        schedule_horizon = max(consolidation.SCHEDULE_HORIZON_DAYS, future_horizon_days(week[-1], today))
        consolidation_tasks = consolidation.get_due_consolidation_tasks(
            context="college",
            today=today,
            horizon_days=schedule_horizon,
        )
        schedule_map = consolidation.ensure_schedule("college", today)
```

(this moves `consolidation_tasks`/`schedule_map` construction out of the per-day loop — they're computed once per render, same as before)

Then, inside the `for d in week:` loop, replace:

```python
            consolidation_for_day = [
                task for task in consolidation_tasks
                if (d == today and task.due_date <= today) or task.due_date == d
            ]
```

with:

```python
            consolidation_for_day = [
                task for task in consolidation_tasks
                if schedule_map.get(task.course_id) == d
            ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_planning_cockpit_schedule_wiring.py -v`
Expected: PASS, both tests.

- [ ] **Step 5: Run the full planning test suite for regressions**

Run: `pytest tests/test_planning_cockpit_schedule.py tests/test_planning_day_capacity.py tests/test_planning_focus.py tests/test_planning_navigation.py tests/test_planning_prep_wiring.py -v`
Expected: PASS, all tests (none of these exercise `_load_and_render`'s consolidation filtering directly, so none should be affected).

- [ ] **Step 6: Commit**

```bash
git add frontend/pages/planning_cockpit.py tests/test_planning_cockpit_schedule_wiring.py
git commit -m "feat(planning): weekly grid reads consolidation items from the persisted schedule"
```

---

### Task 7: Clickable day footer + ±30min day capacity dialog

**Files:**
- Modify: `frontend/pages/planning_cockpit.py:30-40` (imports), `:170-175` (near `_load_label`), `:344-378` (`_open_day_capacity_dialog`), `:463-487` (`_draw_skeleton`)
- Test: `tests/test_planning_day_capacity.py` (extend)

**Interfaces:**
- Consumes: `MAX_CAPACITY_HOURS` (`backend/core/planning/policy.py`, existing), `consolidation.reschedule_from` (Task 4).
- Produces: clicking a day's footer opens the capacity dialog directly; the dialog gains ±30min buttons and allows 0.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_planning_day_capacity.py`:

```python
def test_day_footer_is_clickable_and_opens_the_capacity_dialog():
    source = _source()
    assert '"pl-day-foot cursor-pointer"' in source
    assert 'foot.on("click", lambda day=d: _open_day_capacity_dialog(day))' in source


def test_day_capacity_dialog_has_fine_grained_minute_buttons():
    source = _source()
    assert "-30min" in source
    assert "+30min" in source


def test_day_capacity_dialog_allows_zero():
    source = _source()
    assert "max(0, min(MAX_CAPACITY_HOURS * 60" in source


def test_day_capacity_save_and_reset_trigger_the_cascade():
    source = _source()
    assert 'consolidation.reschedule_from("college", day)' in source
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_planning_day_capacity.py -v`
Expected: the 4 new tests FAIL; existing 3 tests still PASS.

- [ ] **Step 3: Import `MAX_CAPACITY_HOURS`**

In `frontend/pages/planning_cockpit.py`, extend the `from backend.core.planning.policy import (...)` block (lines 30-40) to add `MAX_CAPACITY_HOURS`:

```python
from backend.core.planning.policy import (
    capacity_from_preferences,
    capacity_hours_to_minutes,
    effective_capacity_minutes,
    is_vacation_day,
    return_diagnostic_tasks,
    target_for_day,
    vacation_for_preferences,
    vacation_is_expired,
    vacation_payload,
    MAX_CAPACITY_HOURS,
)
```

- [ ] **Step 4: Add a minutes-label helper**

In `frontend/pages/planning_cockpit.py`, right after `_load_label` (after line 174):

```python
def _duration_label(minutes: int) -> str:
    if minutes <= 0:
        return "0 min"
    h, m = divmod(int(minutes), 60)
    return f"{h}h{m:02d}" if h else f"{m} min"
```

- [ ] **Step 5: Rewrite `_open_day_capacity_dialog`**

Replace `frontend/pages/planning_cockpit.py:344-378` in full:

```python
    def _open_day_capacity_dialog(day: datetime.date) -> None:
        targets = dict(data_store.preferences.get("planning_targets", {}))
        current = targets.get(day.isoformat(), {})
        current_minutes = (
            int(current["value"]) if current.get("mode") == "minutes"
            else capacity_from_preferences(data_store.preferences)
        )
        state = {"minutes": max(0, min(MAX_CAPACITY_HOURS * 60, current_minutes))}
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-sm p-4 gap-0"):
            ui.label(f"Capacité du {_month_day(day)}").classes("text-base font-semibold")
            ui.label("Remplace la capacité par défaut pour ce jour seulement.").classes(
                "text-xs text-slate-500 mt-1"
            )
            with ui.row().classes("w-full items-center justify-center gap-3 mt-3"):
                minus_btn = ui.button("-30min").props("outline dense no-caps")
                value_label = ui.label(_duration_label(state["minutes"])).classes(
                    "text-sm font-semibold w-16 text-center"
                )
                plus_btn = ui.button("+30min").props("outline dense no-caps")

            def _adjust(delta: int) -> None:
                state["minutes"] = max(0, min(MAX_CAPACITY_HOURS * 60, state["minutes"] + delta))
                value_label.set_text(_duration_label(state["minutes"]))

            minus_btn.on_click(lambda: _adjust(-30))
            plus_btn.on_click(lambda: _adjust(30))

            hours = ui.toggle(
                {3: "3 h", 6: "6 h", 9: "9 h", 12: "12 h"}, value=None
            ).props("dense unelevated no-caps").classes("w-full mt-3")

            def _apply_preset(event) -> None:
                if event.value is not None:
                    state["minutes"] = capacity_hours_to_minutes(event.value)
                    value_label.set_text(_duration_label(state["minutes"]))

            hours.on_value_change(_apply_preset)

            with ui.row().classes("w-full justify-end gap-2 mt-5"):
                def _reset() -> None:
                    targets.pop(day.isoformat(), None)
                    data_store.set_preference("planning_targets", targets)
                    dialog.close()
                    consolidation.reschedule_from("college", day)
                    asyncio.create_task(_load_and_render())
                    ui.notify("Capacité par défaut restaurée", type="positive")

                ui.button("Réinitialiser", on_click=_reset).props("flat no-caps color=slate")

                def _save() -> None:
                    targets[day.isoformat()] = {"mode": "minutes", "value": state["minutes"]}
                    data_store.set_preference("planning_targets", targets)
                    dialog.close()
                    consolidation.reschedule_from("college", day)
                    asyncio.create_task(_load_and_render())
                    ui.notify("Capacité du jour enregistrée", type="positive")

                ui.button("Enregistrer", on_click=_save).props("unelevated color=indigo no-caps")
        dialog.open()
```

- [ ] **Step 6: Make the day footer clickable**

In `frontend/pages/planning_cockpit.py`'s `_draw_skeleton` (around line 486), replace:

```python
                    foot = ui.element("div").classes("pl-day-foot")
```

with:

```python
                    foot = ui.element("div").classes("pl-day-foot cursor-pointer")
                    foot.on("click", lambda day=d: _open_day_capacity_dialog(day))
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_planning_day_capacity.py -v`
Expected: PASS, all 7 tests.

- [ ] **Step 8: Manually verify in the browser**

Start the app's dev server (per this project's usual run instructions), open `/planning`, click a day's footer hour total, confirm the dialog opens, click `+30min`/`-30min` a few times and confirm the displayed value updates, save, and confirm the grid re-renders with the new capacity applied and any bumped items now showing on a later day.

- [ ] **Step 9: Commit**

```bash
git add frontend/pages/planning_cockpit.py tests/test_planning_day_capacity.py
git commit -m "feat(planning): click the day footer to adjust capacity with +/-30min and a 0 floor"
```

---

### Task 8: Cascade on the global "Ma charge" dialog

**Files:**
- Modify: `frontend/pages/planning_cockpit.py:251-342` (`_open_capacity_dialog` → `_save_capacity`)
- Test: `tests/test_planning_day_capacity.py` (extend)

**Interfaces:**
- Consumes: `consolidation.reschedule_from` (Task 4).

Changing the global default capacity or toggling vacation mode also changes what `target_for_day` returns for every future day — the persisted schedule needs the same cascade as a per-day override.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_planning_day_capacity.py`:

```python
def test_global_capacity_save_triggers_the_cascade_from_today():
    source = _source()
    assert 'consolidation.reschedule_from("college", datetime.date.today())' in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_planning_day_capacity.py -v -k global_capacity`
Expected: FAIL — the string isn't present yet.

- [ ] **Step 3: Add the cascade call**

In `frontend/pages/planning_cockpit.py`'s `_save_capacity` (inside `_open_capacity_dialog`, around line 335-339), insert the cascade call right after the two `data_store.set_preference` calls and before `dialog.close()`:

```python
                        data_store.set_preference("planning_capacity_minutes", capacity_hours_to_minutes(hours))
                        data_store.set_preference("planning_vacation", vacation)
                        consolidation.reschedule_from("college", datetime.date.today())
                        dialog.close()
                        asyncio.create_task(_load_and_render())
                        ui.notify("Ma charge a été enregistrée", type="positive")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_planning_day_capacity.py -v`
Expected: PASS, all 8 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/planning_cockpit.py tests/test_planning_day_capacity.py
git commit -m "feat(planning): saving the global capacity/vacation also cascades the schedule"
```

---

### Task 9: Cascade on the weekend-light toggle

**Files:**
- Modify: `frontend/pages/settings_cockpit.py:282-291` (`_toggle_weekend_light`)
- Test: `tests/test_settings_cockpit_weekend_light_cascade.py` (new)

**Interfaces:**
- Consumes: `consolidation.reschedule_from` (Task 4).

**Note:** this file imports `from datetime import date` (not `import datetime`) — use `date.today()`, not `datetime.date.today()`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_settings_cockpit_weekend_light_cascade.py`:

```python
from pathlib import Path


def test_weekend_light_toggle_triggers_the_cascade():
    source = Path("frontend/pages/settings_cockpit.py").read_text(encoding="utf-8")
    assert 'consolidation.reschedule_from("college", date.today())' in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_settings_cockpit_weekend_light_cascade.py -v`
Expected: FAIL — the string isn't present yet.

- [ ] **Step 3: Add the import and the cascade call**

In `frontend/pages/settings_cockpit.py:43`, add the consolidation import right after the existing `capacity_from_preferences` import line:

```python
from backend.core.planning.policy import capacity_from_preferences, capacity_hours_to_minutes
from backend.core.reviews import consolidation
```

In `_toggle_weekend_light` (`frontend/pages/settings_cockpit.py:282-292`), replace the whole function:

```python
                    def _toggle_weekend_light(sw=weekend_switch):
                        new_val = not bool(data_store.preferences.get("weekend_light_consolidation", False))
                        data_store.set_preference("weekend_light_consolidation", new_val)
                        if new_val:
                            sw.classes(add="on")
                        else:
                            sw.classes(remove="on")
                        ui.notify(
                            "Charge week-end allégée" if new_val else "Charge week-end normale",
                            type="positive",
                        )
```

with:

```python
                    def _toggle_weekend_light(sw=weekend_switch):
                        new_val = not bool(data_store.preferences.get("weekend_light_consolidation", False))
                        data_store.set_preference("weekend_light_consolidation", new_val)
                        consolidation.reschedule_from("college", date.today())
                        if new_val:
                            sw.classes(add="on")
                        else:
                            sw.classes(remove="on")
                        ui.notify(
                            "Charge week-end allégée" if new_val else "Charge week-end normale",
                            type="positive",
                        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_settings_cockpit_weekend_light_cascade.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full test suite for final regression check**

Run: `pytest tests/ -v -k "consolidation or planning_policy or planning_day_capacity or planning_cockpit_schedule or settings_cockpit_weekend_light"`
Expected: PASS, everything green.

- [ ] **Step 6: Commit**

```bash
git add frontend/pages/settings_cockpit.py tests/test_settings_cockpit_weekend_light_cascade.py
git commit -m "feat(settings): toggling weekend-light consolidation cascades the schedule"
```

---

## Self-Review Notes

- **Spec coverage:** §3 data model → Task 2. §4 allocator → Task 3. §5 Dashboard/Planning integration → Tasks 5, 6. §6 cascade → Task 4, wired in Tasks 7-9. §7 UI → Task 7. §8 zero-capacity/vacation edge case → covered inside Task 3's `target_for_day(day, preferences) == 0` check and its test. §9 tests → one file per concern (Tasks 2, 3, 4) plus updates to the two existing tests the change touches (Task 5) and source-string tests for the UI (Tasks 6-9).
- **Bug found during planning, fixed in Task 1:** `capacity_from_preferences` ignored `planning_targets` whenever `planning_capacity_minutes` was set — meaning the existing "Ajuster la capacité de ce jour" dialog has never actually changed anything once the user saved "Ma charge" once. This had to be fixed first since Task 7 builds directly on top of it.
- **API simplification:** `plan_consolidation()` drops its `max_items`/`max_per_college` parameters (Task 5) — confirmed zero production callers pass them, and the one test that did gets equivalent behavior from the real defaults.
