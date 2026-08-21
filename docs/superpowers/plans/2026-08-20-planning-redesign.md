# Refonte Planning — visibilité fiable + pilotage de la charge — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the Planning weekly grid so it reliably shows lecture (JX cycle + fac-course prep) and consolidation work every day — including future weeks — governed by a single time-budget waterfall, with a unified capacity setting (global + per-day override) and a faster weekly load.

**Architecture:** `PlanningService.plan_day()` moves from "one merged list capped at 5 items" to "two separately-computed lanes" (Lecture consumes the day's minute budget first, Consolidation gets the remainder via the existing diversity-capped `consolidation.select_daily`). `planning_cockpit.py` stops merging consolidation into the lecture task list, adds a new prep-task lane pulled from the existing (already-in-production) `backend/core/prep/` module, and fetches the whole week's Calendar events in one call instead of seven. `daily_budget_min` is retired as a preference; its two real consumers (Dashboard's Sprint EDN projection and Dashboard's list trim) are repointed individually per an explicit decision for each.

**Tech Stack:** Python 3.13, NiceGUI (frontend pages), SQLite (local_store/prep store), pytest.

## Global Constraints

- Preserve all currently-passing tests; `plan_day` keeps working for existing callers that don't pass the new optional parameters (backward-compatible defaults).
- No due_date is ever mutated to "hide" an overflowing item — deferred items keep reappearing via existing `skipped`/`select_daily` mechanics (unchanged convention, see `docs/superpowers/specs/2026-08-20-weekend-light-consolidation-design.md`).
- UI additions follow the existing Linear token system (`frontend/design_tokens.py`): colors via CSS variables, border radius ≤8px, no pill shapes.
- Dashboard's list-truncation behavior (`apply_daily_budget` call in `_cockpit_today.py`) stays a no-op (budget resolves to `0`) — only the Sprint EDN projection input changes, per explicit user decision recorded in the spec.
- Source spec: `docs/superpowers/specs/2026-08-20-planning-redesign-design.md` — consult it for the "why" behind any task below.

---

## Task 1: Prep-task duration keys + aggregated slot builder

**Files:**
- Modify: `backend/core/planning/models.py:19-31` (SLOT_META)
- Modify: `backend/core/planning/service.py:30-39` (_DUR_KEYS), and add a new method after `_slot_from_lacune` (currently ending at `service.py:122`)
- Test: `tests/test_planning_service_waterfall.py` (new file)

**Interfaces:**
- Consumes: `backend.core.prep.models.PrepTask` (fields: `course_id`, `item_number`, `task_type` — one of `"pdf"|"obsidian"|"resume"|"first_read"`).
- Produces: `PlanningService._slot_from_prep_tasks(course_tasks: list[PrepTask], durations: dict) -> PlannedSlot` — consumed by Task 5. `SLOT_META["prep"]` — consumed by any future renderer that looks up slot metadata (not required by `_draw_day`, which sets colors explicitly, but kept consistent with every other slot type).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_planning_service_waterfall.py`:

```python
import datetime

from backend.core.planning.service import planning_service
from backend.core.prep.models import PrepTask


def _prep_task(task_type: str, *, course_id: str = "c187", item_number: str = "187") -> PrepTask:
    return PrepTask(
        id=1, course_id=course_id, item_number=item_number,
        lecture_date=datetime.date(2026, 8, 22),
        calendar_event_id="evt-1", calendar_title="Cours HGE",
        task_type=task_type, status="todo",
        created_at="2026-08-20T10:00:00", updated_at="2026-08-20T10:00:00",
        completed_at=None,
    )


def test_slot_from_prep_tasks_aggregates_missing_subtasks():
    durations = planning_service.get_durations()
    tasks = [_prep_task("pdf"), _prep_task("first_read")]

    slot = planning_service._slot_from_prep_tasks(tasks, durations)

    assert slot.slot_type == "prep"
    assert slot.label == "ITEM 187 – Préparer"
    assert slot.subtitle == "PDF · 1ère lecture"
    assert slot.course_id == "c187"
    assert slot.item_number == "187"
    assert slot.duration_min == durations["prep_pdf"] + durations["lecture"]


def test_slot_from_prep_tasks_sums_all_four_types():
    durations = planning_service.get_durations()
    tasks = [_prep_task(t) for t in ("pdf", "obsidian", "resume", "first_read")]

    slot = planning_service._slot_from_prep_tasks(tasks, durations)

    expected = (
        durations["prep_pdf"] + durations["obsidian"]
        + durations["prep_resume"] + durations["lecture"]
    )
    assert slot.duration_min == expected
    assert slot.subtitle == "PDF · Fiche Obsidian · Résumé · 1ère lecture"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_planning_service_waterfall.py -v`
Expected: FAIL — `AttributeError: 'PlanningService' object has no attribute '_slot_from_prep_tasks'` (and `durations["prep_pdf"]` / `KeyError` if reached).

- [ ] **Step 3: Add the SLOT_META entry**

In `backend/core/planning/models.py`, inside the `SLOT_META` dict (after the `"lecture"` entry, `models.py:30`):

```python
    "lecture":      {"color": "green",  "icon": "auto_stories"},
    "prep":         {"color": "amber",  "icon": "assignment"},
```

- [ ] **Step 4: Add duration keys and the slot builder**

In `backend/core/planning/service.py`, extend `_DUR_KEYS` (`service.py:30-39`):

```python
_DUR_KEYS = {
    "revision":    ("dur_revision",    20),
    "lecture":     ("dur_lecture",     30),
    "anki":        ("dur_anki",        30),
    "qcm":         ("dur_qcm",         30),
    "video_ednpro":("dur_video",       30),
    "obsidian":    ("dur_obsidian",    20),
    "lacune":      ("dur_lacune",      15),
    "fiche_edn":   ("dur_fiche_edn",   20),
    "prep_pdf":    ("dur_prep_pdf",    5),
    "prep_resume": ("dur_prep_resume", 20),
}

_PREP_DURATION_KEY = {"pdf": "prep_pdf", "obsidian": "obsidian", "resume": "prep_resume", "first_read": "lecture"}
_PREP_LABEL = {"pdf": "PDF", "obsidian": "Fiche Obsidian", "resume": "Résumé", "first_read": "1ère lecture"}
_PREP_TYPE_ORDER = ("pdf", "obsidian", "resume", "first_read")
```

Add the method after `_slot_from_lacune` (`service.py:122`, still inside `class PlanningService`):

```python
    # ── Conversion tâches de prépa fac → PlannedSlot ──────────────────────────

    def _slot_from_prep_tasks(self, course_tasks: list, durations: dict) -> PlannedSlot:
        """Un seul bloc par cours, agrégeant ses tâches de prépa fac 'todo' du jour."""
        first = course_tasks[0]
        by_type = {t.task_type: t for t in course_tasks}
        ordered_types = [t for t in _PREP_TYPE_ORDER if t in by_type]
        total = sum(self._dur(_PREP_DURATION_KEY[t], durations) for t in ordered_types)
        subtitle = " · ".join(_PREP_LABEL[t] for t in ordered_types)
        return PlannedSlot(
            slot_type="prep",
            label=f"ITEM {first.item_number} – Préparer",
            subtitle=subtitle,
            duration_min=total,
            color="amber",
            icon="assignment",
            course_id=first.course_id,
            course_title=None,
            item_number=first.item_number,
            source_ref="prep",
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_planning_service_waterfall.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/core/planning/models.py backend/core/planning/service.py tests/test_planning_service_waterfall.py
git commit -m "feat(planning): aggregate fac-prep tasks into one slot per course"
```

---

## Task 2: `plan_day` waterfall — Lecture consumes budget first, Consolidation gets the remainder

**Files:**
- Modify: `backend/core/planning/service.py:144-221` (`plan_day` method)
- Test: `tests/test_planning_service_waterfall.py` (append)

**Interfaces:**
- Consumes: `consolidation.select_daily(tasks, max_items, max_per_college) -> tuple[list, list]` and `consolidation.daily_caps(today, weekend_light) -> tuple[int, int]` (both already exist and are unchanged, `backend/core/reviews/consolidation.py:251` and `:279`). `PlanningService._slot_from_prep_tasks` (Task 1).
- Produces: new `plan_day` signature —
  `plan_day(self, urgent_tasks, today_tasks, active_lacunes, calendar_events=None, max_urgent=8, max_lacunes=3, target_minutes=None, prep_slots=None, consolidation_tasks=None, consolidation_today=None) -> DailyPlan`
  — consumed by Task 5. `max_today` and `target_items` parameters are **removed** (grep confirms no caller outside this file and its tests uses them).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_planning_service_waterfall.py`:

```python
from types import SimpleNamespace


def _review_task(course_id, *, days_overdue=0, priority_score=1.0, review_type="review",
                  college=None, item_number="1"):
    return SimpleNamespace(
        course_id=course_id, item_number=item_number, course_title=f"Cours {course_id}",
        best_pdf_url=None, days_overdue=days_overdue, priority_score=priority_score,
        review_type=review_type, anki=False, nb_lectures=1, qcm_done=True,
        mastery_level="à consolider" if review_type == "consolidation" else "correct",
        college=college or ["Cardiologie"],
    )


def test_urgent_tasks_are_never_trimmed_even_over_budget():
    urgent = [_review_task("u1", days_overdue=3)]  # ~30min via get_next_action
    plan = planning_service.plan_day(urgent, [], [], target_minutes=1)

    assert [s.course_id for s in plan.slots if s.is_urgent] == ["u1"]


def test_lecture_consumes_budget_before_consolidation_gets_any():
    today_tasks = [_review_task("t1")]  # ~30 min, review_type="review"
    consolidation_tasks = [_review_task("c1", review_type="consolidation")]

    plan = planning_service.plan_day(
        [], today_tasks, [], target_minutes=20,  # smaller than the 30min lecture task
        consolidation_tasks=consolidation_tasks, consolidation_today=datetime.date(2026, 8, 24),
    )

    assert all(s.slot_type != "consolidation" for s in plan.slots)
    assert any(getattr(s, "course_id", None) == "c1" for s in plan.skipped)


def test_consolidation_fills_the_remaining_budget():
    consolidation_tasks = [_review_task("c1", review_type="consolidation")]

    plan = planning_service.plan_day(
        [], [], [], target_minutes=120,
        consolidation_tasks=consolidation_tasks, consolidation_today=datetime.date(2026, 8, 24),
    )

    assert any(s.slot_type == "consolidation" and s.course_id == "c1" for s in plan.slots)
    assert plan.skipped == []


def test_consolidation_respects_college_diversity_cap_within_remaining_budget():
    consolidation_tasks = [
        _review_task(f"c{i}", review_type="consolidation", college=["Cardiologie"], priority_score=10 - i)
        for i in range(5)
    ]  # MAX_PER_COLLEGE_PER_DAY (2) will cap this college regardless of remaining minutes

    plan = planning_service.plan_day(
        [], [], [], target_minutes=600,
        consolidation_tasks=consolidation_tasks, consolidation_today=datetime.date(2026, 8, 24),
    )

    kept = [s for s in plan.slots if s.slot_type == "consolidation"]
    assert len(kept) == 2


def test_daily_caps_use_the_planned_day_not_the_real_today(monkeypatch):
    from backend.state.store import data_store

    monkeypatch.setitem(data_store.preferences, "weekend_light_consolidation", True)
    consolidation_tasks = [
        _review_task(f"c{i}", review_type="consolidation", college=["Cardiologie"], priority_score=10 - i)
        for i in range(5)
    ]
    saturday = datetime.date(2026, 8, 29)  # a Saturday in a future week

    plan = planning_service.plan_day(
        [], [], [], target_minutes=600,
        consolidation_tasks=consolidation_tasks, consolidation_today=saturday,
    )

    kept = [s for s in plan.slots if s.slot_type == "consolidation"]
    assert len(kept) == 1  # WEEKEND_MAX_PER_COLLEGE_PER_DAY


def test_prep_slots_are_counted_against_the_lecture_budget():
    from backend.core.planning.models import PlannedSlot

    prep = PlannedSlot(slot_type="prep", label="ITEM 187 – Préparer", subtitle="PDF",
                        duration_min=100, color="amber", icon="assignment", course_id="c187")
    consolidation_tasks = [_review_task("c1", review_type="consolidation")]

    plan = planning_service.plan_day(
        [], [], [], target_minutes=110, prep_slots=[prep],
        consolidation_tasks=consolidation_tasks, consolidation_today=datetime.date(2026, 8, 24),
    )

    assert any(s.slot_type == "prep" for s in plan.slots)
    assert all(s.slot_type != "consolidation" for s in plan.slots)  # only 10min left, task needs more
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_planning_service_waterfall.py -v`
Expected: FAIL — old `plan_day` merges everything into one list with `max_today=5`, has no `consolidation_tasks`/`prep_slots`/`consolidation_today` parameters (`TypeError: unexpected keyword argument`).

- [ ] **Step 3: Rewrite `plan_day`**

Replace `backend/core/planning/service.py:144-221` (the whole `plan_day` method) with:

```python
    def plan_day(
        self,
        urgent_tasks: list,
        today_tasks:  list,
        active_lacunes: list,
        calendar_events: list | None = None,
        max_urgent: int = 8,
        max_lacunes: int = 3,
        target_minutes: int | None = None,
        prep_slots: list | None = None,
        consolidation_tasks: list | None = None,
        consolidation_today: datetime.date | None = None,
    ) -> DailyPlan:
        """
        Génère le planning d'une journée en deux voies :

          1. Lecture  : urgentes (retard) + du jour + lacunes + prépa fac (prep_slots),
                        triées par priorité, consomment `target_minutes` en premier.
                        Les tâches en retard ne sont jamais coupées (mais comptent bien
                        dans le total consommé).
          2. Consolidation : ce qu'il reste de `target_minutes` après la voie Lecture,
                        sélectionnée par urgence avec le plafond diversité-par-collège
                        existant (consolidation.select_daily/daily_caps).

        Tout item écarté (Lecture par le budget, Consolidation par le budget ou le
        plafond diversité) est renvoyé dans `skipped` plutôt que silencieusement perdu.
        """
        durations = self.get_durations()
        lecture_slots: list[PlannedSlot] = []

        # ── Lecture : urgentes ────────────────────────────────────────────────
        for t in sorted(urgent_tasks, key=lambda x: -x.days_overdue)[:max_urgent]:
            lecture_slots.append(self._slot_from_task(t, "urgent"))

        # ── Lecture : du jour ─────────────────────────────────────────────────
        for t in sorted(today_tasks, key=lambda x: -x.priority_score):
            lecture_slots.append(self._slot_from_task(t, "today"))

        # ── Lecture : lacunes ─────────────────────────────────────────────────
        active_statuses = {"active", "à revoir", "récurrente"}
        lacunes_filtered = [
            lc for lc in active_lacunes
            if (lc["status"] or "").lower() in active_statuses
        ]
        lacunes_filtered.sort(key=lambda x: -(x["severity"] or 0))
        for lc in lacunes_filtered[:max_lacunes]:
            lecture_slots.append(self._slot_from_lacune(lc, durations))

        # ── Lecture : prépa fac ───────────────────────────────────────────────
        lecture_slots.extend(prep_slots or [])

        # ── Trim Lecture par le budget (les urgentes ne sont jamais coupées) ──
        skipped: list[PlannedSlot] = []
        lecture_min = 0
        if target_minutes is not None:
            kept: list[PlannedSlot] = []
            used = 0
            for slot in lecture_slots:
                if slot.is_urgent or used + slot.duration_min <= target_minutes:
                    kept.append(slot)
                    used += slot.duration_min
                else:
                    skipped.append(slot)
            lecture_slots = kept
            lecture_min = used
        else:
            lecture_min = sum(s.duration_min for s in lecture_slots)

        # ── Consolidation : ce qu'il reste du budget ─────────────────────────
        consolidation_slots: list[PlannedSlot] = []
        if consolidation_tasks:
            from backend.core.reviews import consolidation
            from backend.state.store import data_store

            weekend_light = bool(data_store.preferences.get("weekend_light_consolidation", False))
            max_items, max_per_college = consolidation.daily_caps(
                today=consolidation_today, weekend_light=weekend_light,
            )
            diversity_selected, diversity_skipped = consolidation.select_daily(
                consolidation_tasks, max_items=max_items, max_per_college=max_per_college,
            )

            remaining = None if target_minutes is None else max(0, target_minutes - lecture_min)
            cons_skipped_tasks = list(diversity_skipped)
            used = 0
            for t in diversity_selected:
                slot = self._slot_from_task(t, "consolidation")
                if remaining is None or used + slot.duration_min <= remaining:
                    consolidation_slots.append(slot)
                    used += slot.duration_min
                else:
                    cons_skipped_tasks.append(t)

            skipped.extend(self._slot_from_task(t, "consolidation") for t in cons_skipped_tasks)

        slots = lecture_slots + consolidation_slots
        total_min = sum(s.duration_min for s in slots)
        cal_busy  = self._calendar_busy_min(calendar_events)
        free_min  = max(0, DEFAULT_STUDY_DAY_MIN - cal_busy)

        logger.debug(
            f"PlanningService.plan_day : {len(slots)} slots, "
            f"{total_min} min estimé, {cal_busy} min Calendar occupé, "
            f"{len(skipped)} en attente"
        )

        return DailyPlan(
            date=datetime.date.today(),
            slots=slots,
            skipped=skipped,
            total_min=total_min,
            is_heavy=total_min > HEAVY_THRESHOLD_MIN,
            calendar_busy_min=cal_busy,
            free_min=free_min,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_planning_service_waterfall.py tests/test_planning_service_consolidation.py -v`
Expected: PASS — including the pre-existing `test_plan_day_marks_consolidation_slots_distinctly` (a consolidation-typed task passed via `today_tasks` still lands with `slot_type="consolidation"`, since `_slot_from_task` self-corrects `source_ref`/`slot_type` from `task.review_type` regardless of which lane called it).

- [ ] **Step 5: Run the full existing planning test suite for regressions**

Run: `pytest tests/test_planning_service_consolidation.py tests/test_planning_focus.py tests/test_planning_cockpit_schedule.py -v`
Expected: PASS (no other file calls `plan_day` with `max_today`/`target_items`; confirm via `grep -rn "max_today\|target_items" --include=*.py .` returning only the method definition/removed lines).

- [ ] **Step 6: Commit**

```bash
git add backend/core/planning/service.py tests/test_planning_service_waterfall.py
git commit -m "feat(planning): plan_day waterfall — lecture consumes budget before consolidation"
```

---

## Task 3: Calendar — fetch a whole week in one call

**Files:**
- Modify: `backend/core/google/calendar_service.py:134-224` (add a new method near `get_events_for_day`)
- Test: `tests/test_calendar_service_events.py` (append)

**Interfaces:**
- Consumes: `backend.core.prep.calendar_parser.event_start_date(event, timezone) -> date | None` (existing).
- Produces: `GoogleCalendarService.get_events_for_range(start: date, end: date) -> dict[date, list[dict]]` — consumed by Task 8.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_calendar_service_events.py`:

```python
def test_get_events_for_range_buckets_events_by_day(fake_calendar_service, monkeypatch):
    import backend.core.google.calendar_service as calendar_module

    events_by_cal = {
        "primary": [
            {"summary": "Lundi", "start": {"dateTime": "2026-08-24T09:00:00+02:00"},
             "end": {"dateTime": "2026-08-24T10:00:00+02:00"}},
            {"summary": "Mercredi", "start": {"dateTime": "2026-08-26T14:00:00+02:00"},
             "end": {"dateTime": "2026-08-26T15:00:00+02:00"}},
        ],
    }
    events_api = _FakeEventsMultiCalendar(events_by_cal)
    fake_calendar_service.service = _FakeServiceMultiCalendar(events_api)
    monkeypatch.setattr(
        calendar_module, "_list_calendar_sources", lambda prefs: [], raising=False,
    )

    result = asyncio.run(
        fake_calendar_service.get_events_for_range(
            datetime.date(2026, 8, 24), datetime.date(2026, 8, 30),
        )
    )

    assert [e["summary"] for e in result[datetime.date(2026, 8, 24)]] == ["Lundi"]
    assert [e["summary"] for e in result[datetime.date(2026, 8, 26)]] == ["Mercredi"]
    assert result[datetime.date(2026, 8, 25)] == []
    assert set(result.keys()) == {datetime.date(2026, 8, 24) + datetime.timedelta(days=i) for i in range(7)}
```

Add the needed imports at the top of `tests/test_calendar_service_events.py` (it currently only imports `asyncio`/`pytest`):

```python
import datetime

from tests.test_planning_calendar_actions import _FakeEventsMultiCalendar, _FakeServiceMultiCalendar
```

(These two fixtures already exist in `tests/test_planning_calendar_actions.py:91-111` at module level — importable as-is, no changes needed there.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_calendar_service_events.py::test_get_events_for_range_buckets_events_by_day -v`
Expected: FAIL — `AttributeError: 'GoogleCalendarService' object has no attribute 'get_events_for_range'`

- [ ] **Step 3: Implement `get_events_for_range`**

In `backend/core/google/calendar_service.py`, add a new method right after `get_events_for_day` (which ends at `calendar_service.py:224` with `return all_events`, add a blank line then the new method — inside the same class):

```python
    async def get_events_for_range(self, start_date: datetime.date, end_date: datetime.date) -> dict:
        """Comme get_events_for_day, mais sur toute une plage en un seul passage par
        calendrier (au lieu d'un appel par jour) — évite N requêtes réseau séquentielles
        quand l'appelant a besoin d'une semaine entière (cf. planning_cockpit.py)."""
        logger.info(f"Fetching calendar events for {start_date}..{end_date}...")
        if not self.service:
            logger.info("Service not initialized, authenticating...")
            try:
                await asyncio.to_thread(self.authenticate)
            except Exception as e:
                logger.error(f"Authentication failed: {e}")
                raise GoogleCalendarAuthError(f"Authentification Google Calendar échouée : {e}") from e

        app_timezone = get_app_timezone()
        start_dt = datetime.datetime.combine(start_date, datetime.time.min, tzinfo=app_timezone)
        end_dt = datetime.datetime.combine(end_date, datetime.time.max, tzinfo=app_timezone)
        time_min = start_dt.isoformat()
        time_max = end_dt.isoformat()

        from backend.config.settings import settings as _cfg
        from backend.state.store import data_store as _store
        from backend.core.planning.calendar_sources import (
            FAC_CALENDAR_ID,
            FAC_CALENDAR_LABEL,
            list_calendar_sources as _list_calendar_sources,
        )

        configured_ids = _cfg.get_calendar_ids()
        preference_sources = _list_calendar_sources(_store.preferences)
        source_labels: dict[str, str] = {FAC_CALENDAR_ID: FAC_CALENDAR_LABEL}
        source_labels.update({s["id"]: s["label"] for s in preference_sources if s["label"]})

        seen_ids: set[str] = set()
        calendar_ids: list[str] = []
        for cid in ["primary", FAC_CALENDAR_ID] + configured_ids + [s["id"] for s in preference_sources]:
            if cid not in seen_ids:
                seen_ids.add(cid)
                calendar_ids.append(cid)

        all_events: list[dict] = []

        async def fetch_calendar(cal_id):
            try:
                events_result = await asyncio.to_thread(
                    lambda: self.service.events().list(
                        calendarId=cal_id,
                        timeMin=time_min,
                        timeMax=time_max,
                        singleEvents=True,
                        orderBy='startTime',
                    ).execute()
                )
                items = events_result.get('items', [])
                label = source_labels.get(cal_id, "")
                for event in items:
                    event["_synapse_source_label"] = label
                    event["_synapse_calendar_id"] = cal_id
                return items
            except Exception as e:
                logger.error(f"Error fetching calendar {cal_id}: {e}")
                return []

        # Même contrainte que get_events_for_day : séquentiel entre calendriers.
        for cid in calendar_ids:
            all_events.extend(await fetch_calendar(cid))

        from backend.core.prep.calendar_parser import event_start_date

        events_by_day: dict[datetime.date, list[dict]] = {
            start_date + datetime.timedelta(days=i): []
            for i in range((end_date - start_date).days + 1)
        }
        for event in all_events:
            day = event_start_date(event, app_timezone)
            if day in events_by_day:
                events_by_day[day].append(event)

        return events_by_day
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_calendar_service_events.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/google/calendar_service.py tests/test_calendar_service_events.py
git commit -m "feat(calendar): add get_events_for_range for single-pass weekly fetch"
```

---

## Task 4: Dashboard — repoint the two `daily_budget_min` reads

**Files:**
- Modify: `frontend/pages/dashboard/_cockpit_today.py:266-270,296-301`
- Test: `tests/test_cockpit_today_capacity.py` (new file)

**Interfaces:**
- Consumes: `backend.core.planning.policy.capacity_from_preferences(preferences: dict, day_iso: str | None = None) -> int` (existing, tested in `tests/test_planning_policy.py`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_cockpit_today_capacity.py`:

```python
"""daily_budget_min est retiré ; ses deux usages pointent la vraie capacité —
sauf le tronquage, qui reste désactivé (cf. spec §3, décision explicite)."""
from pathlib import Path


def test_daily_budget_min_is_fully_removed():
    source = Path("frontend/pages/dashboard/_cockpit_today.py").read_text(encoding="utf-8")
    assert "daily_budget_min" not in source


def test_sprint_projection_uses_the_real_capacity():
    source = Path("frontend/pages/dashboard/_cockpit_today.py").read_text(encoding="utf-8")
    assert "capacity_from_preferences(data_store.preferences)" in source


def test_dashboard_trim_stays_disabled_without_a_day_override():
    source = Path("frontend/pages/dashboard/_cockpit_today.py").read_text(encoding="utf-8")
    assert 'budget = target.get("value", 0) if target.get("mode") == "minutes" else 0' in source
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cockpit_today_capacity.py -v`
Expected: FAIL (current source still contains `daily_budget_min` twice, no `capacity_from_preferences` call).

- [ ] **Step 3: Edit the two call sites**

In `frontend/pages/dashboard/_cockpit_today.py`, line 268, replace:

```python
        budget = target.get("value", 0) if target.get("mode") == "minutes" else data_store.preferences.get("daily_budget_min", 0)
```

with:

```python
        budget = target.get("value", 0) if target.get("mode") == "minutes" else 0
```

At line 299 (inside the `project_to_exam(...)` call), replace:

```python
            daily_capacity_minutes=int(data_store.preferences.get("daily_budget_min", 60) or 60),
```

with:

```python
            daily_capacity_minutes=capacity_from_preferences(data_store.preferences),
```

Add the import near the top of the file, alongside the other `backend.core.planning` imports (check existing import block for `from backend.core.planning...` and add next to it; if none exists yet, add near the other `backend.core.*` imports):

```python
from backend.core.planning.policy import capacity_from_preferences
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cockpit_today_capacity.py -v`
Expected: PASS

- [ ] **Step 5: Run the Sprint EDN / recommendation regression suites**

Run: `pytest tests/test_edn_trajectory.py tests/test_recommendation_service.py tests/test_planning_policy.py -v`
Expected: PASS (these test the underlying functions being composed, not the call site — confirms no signature drift).

- [ ] **Step 6: Commit**

```bash
git add frontend/pages/dashboard/_cockpit_today.py tests/test_cockpit_today_capacity.py
git commit -m "fix(dashboard): stop reading the dead daily_budget_min preference"
```

---

## Task 5: Planning — stop merging consolidation, wire prep tasks and the new `plan_day` params

**Files:**
- Modify: `frontend/pages/planning_cockpit.py:672-743` (`_load_and_render`)
- Test: `tests/test_planning_prep_wiring.py` (new file)

**Interfaces:**
- Consumes: `backend.core.prep.store.list_prep_tasks(day, statuses) -> list[PrepTask]` (existing), `PlanningService._slot_from_prep_tasks` (Task 1), new `plan_day` signature (Task 2).
- Produces: per-day `prep_slots` list, passed into `plan_day` — consumed by Task 6 (`_draw_day` rendering) and already exercised by Task 2's tests for `plan_day` itself.

- [ ] **Step 1: Write the failing test**

Create `tests/test_planning_prep_wiring.py` — a source-level smoke test in the same style as `tests/test_planning_navigation.py:23-27` (the codebase's established pattern for asserting NiceGUI wiring that isn't practically unit-testable in isolation):

```python
"""La grille Planning ne fusionne plus consolidation dans 'due', et calcule
les blocs de prépa fac par jour (cf. spec §1/§2)."""
from pathlib import Path


def _source() -> str:
    return Path("frontend/pages/planning_cockpit.py").read_text(encoding="utf-8")


def test_consolidation_is_no_longer_merged_into_due():
    assert "due = due + consolidation_for_day" not in _source()


def test_plan_day_receives_consolidation_as_a_separate_pool():
    source = _source()
    assert "consolidation_tasks=consolidation_for_day" in source
    assert "consolidation_today=d" in source


def test_prep_tasks_are_fetched_and_aggregated_per_course():
    source = _source()
    assert "list_prep_tasks(day=d" in source
    assert "_slot_from_prep_tasks(" in source
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_planning_prep_wiring.py -v`
Expected: FAIL — current source still merges `due = due + consolidation_for_day` and calls `plan_day(urgent, due, lacunes_day, target_minutes=target_minutes)`.

- [ ] **Step 3: Rewrite the per-day loop in `_load_and_render`**

In `frontend/pages/planning_cockpit.py`, replace the loop body currently at `planning_cockpit.py:706-725`:

```python
        plans = []
        for d in week:
            urgent, due = tasks_for_day(all_tasks, d, today)
            consolidation_for_day = [
                task for task in consolidation_tasks
                if (d == today and task.due_date <= today) or task.due_date == d
            ]
            due = due + consolidation_for_day
            lacunes_day = active_lacunes if d == today else []
            target_minutes = target_for_day(d, data_store.preferences)
            if target_minutes == 0 and is_vacation_day(d, vacation_for_preferences(data_store.preferences)):
                urgent, due, lacunes_day = [], [], []
            plan = planning_service.plan_day(
                urgent,
                due,
                lacunes_day,
                target_minutes=target_minutes,
            )
            plan.date = d
            plans.append(plan)
```

with:

```python
        from backend.core.prep.store import list_prep_tasks
        from itertools import groupby
        from backend.core.planning.service import planning_service as _ps

        durations = planning_service.get_durations()
        plans = []
        for d in week:
            urgent, due = tasks_for_day(all_tasks, d, today)
            consolidation_for_day = [
                task for task in consolidation_tasks
                if (d == today and task.due_date <= today) or task.due_date == d
            ]
            lacunes_day = active_lacunes if d == today else []
            target_minutes = target_for_day(d, data_store.preferences)
            if target_minutes == 0 and is_vacation_day(d, vacation_for_preferences(data_store.preferences)):
                urgent, due, lacunes_day, consolidation_for_day = [], [], [], []

            prep_tasks_today = sorted(list_prep_tasks(day=d, statuses=("todo",)), key=lambda t: t.course_id)
            prep_slots = [
                _ps._slot_from_prep_tasks(list(group), durations)
                for _, group in groupby(prep_tasks_today, key=lambda t: t.course_id)
            ]

            plan = planning_service.plan_day(
                urgent,
                due,
                lacunes_day,
                target_minutes=target_minutes,
                prep_slots=prep_slots,
                consolidation_tasks=consolidation_for_day,
                consolidation_today=d,
            )
            plan.date = d
            plans.append(plan)
```

(`_ps._slot_from_prep_tasks` is a "protected" method called from outside its class — matches the existing codebase convention already visible in this same file, e.g. direct access patterns via the `planning_service` singleton elsewhere; if the reviewer prefers, promote it to a public `slot_from_prep_tasks` in Task 1 instead — either is fine, keep it consistent.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_planning_prep_wiring.py -v`
Expected: PASS

- [ ] **Step 5: Run the broader Planning test suite for regressions**

Run: `pytest tests/test_planning_navigation.py tests/test_planning_focus.py tests/test_planning_cockpit_schedule.py tests/test_planning_calendar_sources.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/pages/planning_cockpit.py tests/test_planning_prep_wiring.py
git commit -m "feat(planning): stop merging consolidation into lecture, wire fac-prep slots"
```

---

## Task 6: Planning — grouped day-cell UI (Lecture / Consolidation), overflow badge, prep-block dialog

**Files:**
- Modify: `frontend/pages/planning_cockpit.py:94-153` (`_CSS`), `:449-490` (`_draw_day`)
- Test: `tests/test_planning_prep_wiring.py` (append)

**Interfaces:**
- Consumes: `PlannedSlot.slot_type` (`"prep"` and `"consolidation"` distinguish the two non-Lecture-default groups), `DailyPlan.skipped` (Task 2), `frontend.components.course_prep_task_row.course_prep_task_row`, `backend.core.prep.service.validate_prep_task`, `frontend.components.course_quick_actions.open_course_prep_action` (all existing, already used identically in `_cockpit_today.py:415-427`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_planning_prep_wiring.py`:

```python
def test_day_cell_renders_two_labelled_groups():
    source = _source()
    assert '"LECTURE"' in source or "'LECTURE'" in source
    assert '"CONSOLIDATION"' in source or "'CONSOLIDATION'" in source


def test_overflow_badge_uses_skipped_count():
    source = _source()
    assert "pl-day-overflow" in source
    assert "plan.skipped" in source


def test_prep_block_opens_a_dialog_instead_of_navigating():
    source = _source()
    assert "open_course_prep_action" in source
    assert "validate_prep_task" in source
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_planning_prep_wiring.py -v`
Expected: FAIL (3 new tests) — none of these strings exist yet in `_draw_day`/`_CSS`.

- [ ] **Step 3: Add CSS for the group headers and overflow badge**

In `frontend/pages/planning_cockpit.py`, inside `_CSS` (after the `.pl-block-sub` rule at `planning_cockpit.py:139`), add:

```css
.pl-group-label { font-size:10px; text-transform:uppercase; letter-spacing:.04em; color:var(--text-dim);
  font-weight:600; margin:6px 0 2px; }
.pl-group-label:first-child { margin-top:0; }
.pl-day-overflow { color:var(--text-dim); font-weight:600; margin-left:6px; }
```

- [ ] **Step 4: Rewrite `_draw_day` to render two groups, the overflow badge, and the prep dialog**

Replace `_draw_day` (`planning_cockpit.py:449-490`) with:

```python
    def _open_prep_dialog(slot) -> None:
        from backend.core.prep.store import list_prep_tasks
        from backend.core.prep.service import validate_prep_task
        from frontend.components.course_prep_task_row import course_prep_task_row
        from frontend.components.course_quick_actions import open_course_prep_action

        tasks = [t for t in list_prep_tasks(statuses=("todo", "done")) if t.course_id == slot.course_id]
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-md p-4 gap-2"):
            ui.label(slot.label).classes("text-base font-semibold")

            def _validate(task) -> None:
                try:
                    validate_prep_task(task.id)
                except (KeyError, ValueError) as exc:
                    ui.notify(str(exc), type="warning")
                    return
                dialog.close()
                asyncio.create_task(_load_and_render())
                ui.notify(f"Préparation validée : ITEM {task.item_number}", type="positive")

            def _open(task) -> None:
                open_course_prep_action(task, refresh_fn=lambda: asyncio.create_task(_load_and_render()))

            for task in tasks:
                if task.status == "todo":
                    course_prep_task_row(task, on_open=_open, on_validate=_validate)
            ui.button("Fermer", on_click=dialog.close).props("flat no-caps color=slate").classes("self-end mt-2")
        dialog.open()

    def _draw_slot_block(slot) -> None:
        slot_classes = "pl-block pl-block-task"
        if slot.slot_type == "consolidation":
            slot_classes += " pl-block-consolidation"
        if slot.slot_type == "prep":
            block = ui.element("div").classes(slot_classes + " pl-block-clickable").tooltip(slot.label)
            block.on("click", lambda s=slot: _open_prep_dialog(s))
        else:
            target = block_target(slot.slot_type, getattr(slot, "course_id", None))
            if target:
                slot_classes += " pl-block-clickable"
            block = ui.element("div").classes(slot_classes).tooltip(slot.label)
            if target:
                block.on("click", lambda route=target: ui.navigate.to(route))
        with block:
            ui.label(slot.label).classes("pl-block-title")
            if slot.subtitle:
                ui.label(f"{slot.subtitle} · {slot.duration_min} min").classes("pl-block-sub")

    def _draw_day(idx: int, d: datetime.date, plan, events: list) -> None:
        ref = day_refs[idx]
        body = ref["body"]
        body.clear()
        with body:
            manual_entries = _manual_entries_by_day.get(d.isoformat(), [])
            if not plan.slots and not events and not manual_entries:
                ui.label("Rien de prévu").classes("pl-day-empty")

            lecture_slots = [s for s in plan.slots if s.slot_type != "consolidation"]
            consolidation_slots = [s for s in plan.slots if s.slot_type == "consolidation"]

            if lecture_slots:
                ui.label("LECTURE").classes("pl-group-label")
                for slot in lecture_slots:
                    _draw_slot_block(slot)
            if consolidation_slots:
                ui.label("CONSOLIDATION").classes("pl-group-label")
                for slot in consolidation_slots:
                    _draw_slot_block(slot)

            for entry in manual_entries:
                target = block_target("manual", entry["course_id"])
                classes = "pl-block pl-block-task" + (" pl-block-clickable" if target else "")
                block = ui.element("div").classes(classes)
                if target:
                    block.on("click", lambda route=target: ui.navigate.to(route))
                with block:
                    title = f"{entry['course_title']} · {entry['activity_type']}"
                    ui.label(title).classes("pl-block-title")
                    ui.label(f"Planifié manuellement · {entry['duration_minutes']} min").classes("pl-block-sub")
            for ev in events:
                title = event_display_title(ev)
                dur = _event_duration_min(ev)
                with ui.element("div").classes("pl-block pl-block-event").tooltip(title):
                    ui.label(title).classes("pl-block-title")
                    if dur:
                        h, m = divmod(dur, 60)
                        ui.label(f"{h}h{m:02d}" if h else f"{dur} min").classes("pl-block-sub")
        manual_total = sum(entry["duration_minutes"] for entry in _manual_entries_by_day.get(d.isoformat(), []))
        foot_text = _load_label(plan.total_min + manual_total)
        if plan.skipped:
            foot_text += f" · +{len(plan.skipped)} en attente"
        ref["foot"].set_text(foot_text)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_planning_prep_wiring.py -v`
Expected: PASS (6 tests total in this file)

- [ ] **Step 6: Run the full Planning navigation suite for regressions**

Run: `pytest tests/test_planning_navigation.py -v`
Expected: PASS — `block_target`/`event_display_title` are untouched; `test_day_cells_wire_the_click_handler` still finds `block_target(` and `pl-block-clickable` in the source.

- [ ] **Step 7: Commit**

```bash
git add frontend/pages/planning_cockpit.py tests/test_planning_prep_wiring.py
git commit -m "feat(planning): render Lecture/Consolidation as labelled groups with an overflow badge"
```

---

## Task 7: Planning — per-day capacity override

**Files:**
- Modify: `frontend/pages/planning_cockpit.py:492-510` (`_open_day_actions`), add a new function near `_open_capacity_dialog` (`planning_cockpit.py:247-338`)
- Test: `tests/test_planning_day_capacity.py` (new file)

**Interfaces:**
- Consumes: `backend.core.planning.policy.capacity_from_preferences`, `capacity_hours_to_minutes` (existing, already imported in this file per `planning_cockpit.py:30-36`).
- Produces: writes `data_store.preferences["planning_targets"][day_iso] = {"mode": "minutes", "value": int}` — already read by `policy.capacity_from_preferences` (Task-independent, pre-existing plumbing) and by `_cockpit_today.py`'s `target` lookup (Task 4, untouched logic).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_planning_day_capacity.py`:

```python
from pathlib import Path


def _source() -> str:
    return Path("frontend/pages/planning_cockpit.py").read_text(encoding="utf-8")


def test_day_actions_menu_offers_a_capacity_override():
    assert "Ajuster la capacité de ce jour" in _source()


def test_day_capacity_dialog_writes_planning_targets():
    source = _source()
    assert '"mode": "minutes"' in source
    assert 'data_store.set_preference("planning_targets", targets)' in source


def test_day_capacity_dialog_can_reset_to_the_global_default():
    assert "targets.pop(day.isoformat(), None)" in _source()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_planning_day_capacity.py -v`
Expected: FAIL — none of this exists yet.

- [ ] **Step 3: Add the day-capacity dialog**

In `frontend/pages/planning_cockpit.py`, add a new function right after `_open_capacity_dialog` ends (`planning_cockpit.py:338`, the line `dialog.open()` closing that function):

```python
    def _open_day_capacity_dialog(day: datetime.date) -> None:
        targets = dict(data_store.preferences.get("planning_targets", {}))
        current = targets.get(day.isoformat(), {})
        current_hours = (
            current["value"] // 60 if current.get("mode") == "minutes"
            else capacity_from_preferences(data_store.preferences) // 60
        )
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-sm p-4 gap-0"):
            ui.label(f"Capacité du {_month_day(day)}").classes("text-base font-semibold")
            ui.label("Remplace la capacité par défaut pour ce jour seulement.").classes(
                "text-xs text-slate-500 mt-1"
            )
            hours = ui.toggle(
                {3: "3 h", 6: "6 h", 9: "9 h", 12: "12 h"}, value=current_hours
            ).props("dense unelevated no-caps").classes("w-full mt-3")

            with ui.row().classes("w-full justify-end gap-2 mt-5"):
                def _reset() -> None:
                    targets.pop(day.isoformat(), None)
                    data_store.set_preference("planning_targets", targets)
                    dialog.close()
                    asyncio.create_task(_load_and_render())
                    ui.notify("Capacité par défaut restaurée", type="positive")

                ui.button("Réinitialiser", on_click=_reset).props("flat no-caps color=slate")

                def _save() -> None:
                    targets[day.isoformat()] = {"mode": "minutes", "value": capacity_hours_to_minutes(hours.value)}
                    data_store.set_preference("planning_targets", targets)
                    dialog.close()
                    asyncio.create_task(_load_and_render())
                    ui.notify("Capacité du jour enregistrée", type="positive")

                ui.button("Enregistrer", on_click=_save).props("unelevated color=indigo no-caps")
        dialog.open()
```

- [ ] **Step 4: Add the menu entry**

In `_open_day_actions` (`planning_cockpit.py:492-510`), after the "Créer un événement Google Calendar" button (ends around `planning_cockpit.py:508`), add:

```python
                    ui.button(
                        "Ajuster la capacité de ce jour",
                        icon="tune",
                        on_click=lambda day=day: (dialog.close(), _open_day_capacity_dialog(day)),
                    ).props("outline no-caps unelevated").classes("w-full justify-start")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_planning_day_capacity.py -v`
Expected: PASS

- [ ] **Step 6: Run the Planning navigation suite for regressions**

Run: `pytest tests/test_planning_navigation.py tests/test_planning_calendar_actions.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/pages/planning_cockpit.py tests/test_planning_day_capacity.py
git commit -m "feat(planning): let a single day override the default daily capacity"
```

---

## Task 8: Planning — one weekly Calendar fetch instead of seven

**Files:**
- Modify: `frontend/pages/planning_cockpit.py:727-735` (the per-day Calendar loop inside `_load_and_render`)
- Test: `tests/test_planning_prep_wiring.py` (append)

**Interfaces:**
- Consumes: `GoogleCalendarService.get_events_for_range` (Task 3).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_planning_prep_wiring.py`:

```python
def test_week_load_fetches_calendar_events_once_per_week():
    source = _source()
    assert "get_events_for_range(" in source
    assert "get_events_for_day(" not in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_planning_prep_wiring.py::test_week_load_fetches_calendar_events_once_per_week -v`
Expected: FAIL — the file still calls `get_events_for_day` in a loop.

- [ ] **Step 3: Replace the sequential day loop**

In `frontend/pages/planning_cockpit.py`, replace (`planning_cockpit.py:727-735`):

```python
        # Séquentiel, jamais en parallèle : le client Google Calendar n'est pas
        # thread-safe entre appels concurrents (cf. calendar_service.get_events_for_day
        # et todo.py::_load_week_ajoute — même contrainte déjà documentée ailleurs).
        for idx, (d, plan) in enumerate(zip(week, plans)):
            try:
                events = await calendar_service.get_events_for_day(d)
            except Exception:
                events = []
            _draw_day(idx, d, plan, events or [])
```

with:

```python
        try:
            events_by_day = await calendar_service.get_events_for_range(week[0], week[-1])
        except Exception:
            events_by_day = {}
        for idx, (d, plan) in enumerate(zip(week, plans)):
            _draw_day(idx, d, plan, events_by_day.get(d, []))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_planning_prep_wiring.py -v`
Expected: PASS (all tests in this file)

- [ ] **Step 5: Run the full Planning suite for regressions**

Run: `pytest tests/test_planning_navigation.py tests/test_planning_focus.py tests/test_planning_cockpit_schedule.py tests/test_planning_calendar_sources.py tests/test_planning_calendar_actions.py tests/test_planning_day_capacity.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/pages/planning_cockpit.py tests/test_planning_prep_wiring.py
git commit -m "perf(planning): fetch the whole week's Calendar events in one call"
```

---

## Task 9: Settings — global capacity control in PLANIFICATION EDN

**Files:**
- Modify: `frontend/pages/settings_cockpit.py:41-44` (imports), `:248` (insert before the weekend-light block)
- Test: `tests/test_settings_planning_capacity.py` (new file)

**Interfaces:**
- Consumes: `backend.core.planning.policy.capacity_from_preferences`, `capacity_hours_to_minutes` (existing).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_settings_planning_capacity.py`:

```python
from pathlib import Path


def test_settings_page_exposes_a_global_capacity_control():
    source = Path("frontend/pages/settings_cockpit.py").read_text(encoding="utf-8")
    assert "Capacité quotidienne" in source
    assert '"planning_capacity_minutes"' in source
    assert "capacity_hours_to_minutes" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_settings_planning_capacity.py -v`
Expected: FAIL — no such control exists yet in `settings_cockpit.py`.

- [ ] **Step 3: Add the import**

In `frontend/pages/settings_cockpit.py`, after the existing `from backend.state.store import data_store` (`settings_cockpit.py:44`):

```python
from backend.core.planning.policy import capacity_from_preferences, capacity_hours_to_minutes
```

- [ ] **Step 4: Add the capacity control**

In `frontend/pages/settings_cockpit.py`, right before the "Charge allégée le week-end" block (`settings_cockpit.py:248`), insert:

```python
                with ui.element("div").classes("se-appearance-row"):
                    with ui.column().classes("gap-0"):
                        ui.label("Capacité quotidienne").classes("se-appearance-label")
                        ui.label(
                            "Ta charge de référence, utilisée par Planning et la projection Sprint EDN."
                        ).classes("se-appearance-sub")

                    capacity_toggle = ui.toggle(
                        {3: "3 h", 6: "6 h", 9: "9 h", 12: "12 h"},
                        value=capacity_from_preferences(data_store.preferences) // 60,
                    ).props("dense unelevated no-caps")

                    def _set_capacity(e, toggle=capacity_toggle) -> None:
                        data_store.set_preference("planning_capacity_minutes", capacity_hours_to_minutes(e.value))
                        ui.notify("Capacité quotidienne mise à jour", type="positive")

                    capacity_toggle.on_value_change(_set_capacity)

```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_settings_planning_capacity.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/pages/settings_cockpit.py tests/test_settings_planning_capacity.py
git commit -m "feat(settings): expose the global daily capacity in Paramètres"
```

---

## Final check

- [ ] **Run the entire modified-area test suite once more, end to end**

Run:
```bash
pytest tests/test_planning_service_waterfall.py tests/test_planning_service_consolidation.py \
       tests/test_calendar_service_events.py tests/test_cockpit_today_capacity.py \
       tests/test_planning_prep_wiring.py tests/test_planning_day_capacity.py \
       tests/test_settings_planning_capacity.py tests/test_planning_navigation.py \
       tests/test_planning_focus.py tests/test_planning_cockpit_schedule.py \
       tests/test_planning_calendar_sources.py tests/test_planning_calendar_actions.py \
       tests/test_edn_trajectory.py tests/test_recommendation_service.py tests/test_planning_policy.py -v
```
Expected: PASS, all tests.

- [ ] **Manual verification** (dev server, per the `run` skill): open Planning, navigate to next week, confirm Lecture/Consolidation groups render, a fac-prep block (if any course is due in the next 1-2 days) shows one aggregated line, the week loads visibly faster than before, and Paramètres → PLANIFICATION EDN shows the new capacity control in sync with Planning's "Ma charge" dialog.
