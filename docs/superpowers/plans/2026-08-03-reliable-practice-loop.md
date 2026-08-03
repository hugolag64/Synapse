# Reliable Practice Loop (7.1–7.7) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every practice-session result complete, correctly scored, attributed to the right EDN item, and safe to use by mastery and planning.

**Architecture:** Extend the local SQLite contract with additive, idempotent migrations for completion state, per-proposition corrections, and question-to-item links. Keep correction entirely server-side, expose its mode and state through the QCM API, then make mastery and retention consume only completed, attributable evidence. Centralize business time in settings and remove hard-coded time zones.

**Tech Stack:** Python 3, FastAPI, NiceGUI/React QCM reader, SQLite, pytest, `zoneinfo`.

## Global Constraints

- Migrations must be additive and idempotent; historical sessions must remain readable.
- No network, Gemini, EDNpro, Hypocampus, Calendar API, or external writes are allowed in tests.
- A session can affect mastery only once and only after every question is corrected.
- `score_mode=edn` is allowed only when proposition ranks are known; all other closed questions are explicitly `training`.
- Business-date default is exactly `Europe/Paris`; timestamps already persisted are not rewritten.
- Preserve the user's existing dirty files and do not stage, commit, or push without separate authorization.

---

### Task 1: Establish the database and business-time foundations

**Files:**
- Modify: `backend/config/settings.py`
- Modify: `backend/core/reviews/local_store.py:96-450`
- Modify: `tests/test_local_store.py`
- Create: `tests/test_app_timezone.py`

**Interfaces:**
- Produces `APP_TIMEZONE`, `now_local() -> datetime.datetime`, `business_today() -> datetime.date`.
- Produces `local_store._migrate_reliable_practice_loop() -> None` invoked by `init_db()`.
- Adds session columns `completion_state`, `score_mode`, `score_reason` and tables `ai_practice_attempt_propositions` and `ai_practice_question_items`.

- [ ] **Step 1: Write the failing time-zone tests.**

```python
from backend.config.settings import APP_TIMEZONE, business_today, now_local

def test_business_time_defaults_to_paris():
    assert APP_TIMEZONE.key == "Europe/Paris"
    assert now_local().tzinfo == APP_TIMEZONE
    assert business_today() == now_local().date()
```

- [ ] **Step 2: Run the new test and confirm it fails because the setting remains `Indian/Reunion`.**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_app_timezone.py -q`

Expected: FAIL on `APP_TIMEZONE.key`.

- [ ] **Step 3: Implement the single time service.**

```python
APP_TIMEZONE = zoneinfo.ZoneInfo("Europe/Paris")

def now_local() -> datetime.datetime:
    return datetime.datetime.now(APP_TIMEZONE)

def business_today() -> datetime.date:
    return now_local().date()
```

Make `local_store._now()` call `now_local()`; do not retain a local Reunion constant.

- [ ] **Step 4: Re-run the time-zone tests.**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_app_timezone.py tests/test_local_store.py -q`

Expected: PASS after updating assertions that encoded Reunion rather than business time.

- [ ] **Step 5: Write migration tests before migration code.**

```python
def test_reliable_practice_migration_is_idempotent(practice_db):
    local_store.init_db()
    local_store.init_db()
    with local_store._conn() as con:
        columns = {row["name"] for row in con.execute("PRAGMA table_info(ai_practice_sessions)")}
        assert {"completion_state", "score_mode", "score_reason"} <= columns
        assert con.execute("SELECT 1 FROM sqlite_master WHERE name='ai_practice_attempt_propositions'").fetchone()
```

- [ ] **Step 6: Run the migration test and confirm it fails on missing schema.**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_ai_practice.py::test_reliable_practice_migration_is_idempotent -q`

Expected: FAIL because the new columns/table do not exist.

- [ ] **Step 7: Add the additive migration.**

Add missing columns through `PRAGMA table_info`, create the two link tables with foreign keys and indexes, then backfill existing rows:

```sql
UPDATE ai_practice_sessions
SET completion_state = CASE
  WHEN mastery_recorded_at IS NOT NULL THEN 'recorded'
  WHEN completed_at IS NOT NULL THEN 'scored'
  ELSE 'draft'
END
WHERE completion_state IS NULL OR completion_state = '';
```

Use `training` as the legacy score mode only for sessions that already have a score.

- [ ] **Step 8: Re-run migration and existing store tests.**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_ai_practice.py tests/test_local_store.py tests/test_app_timezone.py -q`

Expected: PASS.

### Task 2: Make finalization complete, non-blocking, and idempotent (7.1, 7.3)

**Files:**
- Modify: `backend/core/reviews/local_store.py:2030-2140`
- Modify: `backend/core/practice/mastery.py`
- Modify: `backend/api/qcm.py:118-166`
- Modify: `tests/test_ai_practice.py`
- Create: `tests/test_qcm_api_completion.py`

**Interfaces:**
- `finalize_ai_practice_session(session_id) -> dict | None` returns `completion_state`, `missing_positions`, `answered_count`, and `scored_count`.
- `record_ai_practice_mastery(session_id)` accepts only a `scored` session and marks it `recorded` once.
- `POST /complete` returns HTTP 409 and `missing_positions` for an incomplete session.

- [ ] **Step 1: Write failing completion tests.**

```python
def test_partial_answers_do_not_complete_or_record_mastery(practice_db):
    session_id = _two_closed_question_session()
    _answer_first_question(session_id)
    summary = local_store.finalize_ai_practice_session(session_id)
    assert summary["completion_state"] == "draft"
    assert summary["missing_positions"] == [2]
    assert summary["completed_at"] is None
    assert record_ai_practice_mastery(session_id) is None

def test_incorrect_answer_finishes_even_when_lacune_creation_fails(practice_db, monkeypatch):
    session_id = _one_closed_question_session()
    _answer_incorrectly(session_id)
    monkeypatch.setattr(local_store, "add_weak_point", lambda **_: (_ for _ in ()).throw(RuntimeError()))
    assert local_store.finalize_ai_practice_session(session_id)["completion_state"] == "scored"
```

- [ ] **Step 2: Run the tests and confirm the partial-session test fails under current behavior.**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_ai_practice.py -k "partial or incorrect_answer_finishes" -q`

Expected: FAIL because a partial attempt currently sets `completed_at` and `record_ai_practice_mastery()` finalizes again.

- [ ] **Step 3: Refactor finalization into a single transaction.**

Within one connection, select the latest non-empty attempt per question; derive missing positions from `ai_practice_session_questions`; require a score for every latest attempt; set state to `scored` only when none are missing. Move weak-point detection after that transaction, query `prompt`, and catch/log only its own exception.

- [ ] **Step 4: Stop mastery from calling finalization.**

```python
session = local_store.get_ai_practice_session_summary(session_id)
if not session or session["completion_state"] != "scored":
    return None
```

After a successful evaluation, atomically set `mastery_recorded_at` and `completion_state='recorded'`; repeated calls return `None`.

- [ ] **Step 5: Adapt the endpoint and write its red test.**

```python
response = client.post(f"/api/qcm/sessions/{session_id}/complete")
assert response.status_code == 409
assert response.json()["detail"]["missing_positions"] == [2]
```

- [ ] **Step 6: Make `/complete` map `draft` with missing positions to HTTP 409 and keep completed calls stable.**

- [ ] **Step 7: Run completion/API tests.**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_ai_practice.py tests/test_qcm_api_completion.py -q`

Expected: PASS.

### Task 3: Centralize scoring and persist proposition-level correction (7.2)

**Files:**
- Create: `backend/core/practice/scoring.py`
- Modify: `backend/api/qcm.py`
- Modify: `backend/core/reviews/local_store.py`
- Modify: `frontend/components/qcm_replay.py`
- Modify: `frontend/react/qcm-app/src/` (the active result presentation file discovered by `rg`)
- Create: `tests/test_practice_scoring.py`
- Modify: `tests/test_scoring_edn.py`

**Interfaces:**
- `score_closed_attempt(response, choices) -> ScoredAttempt` returns score percent, mode, reason, and proposition rows.
- `local_store.replace_ai_practice_attempt_propositions(attempt_id, rows) -> None`.
- Correction rows expose `score_mode`, `score_reason`, and `propositions`.

- [ ] **Step 1: Write pure scorer tests before adding the scorer.**

```python
def test_ranked_question_uses_official_edn_scale():
    result = score_closed_attempt("A", ranked_choices())
    assert result.score_mode == "edn"
    assert result.score_percent == 50.0
    assert result.propositions[0].discordance == "omission"

def test_question_without_rank_is_explicitly_training():
    result = score_closed_attempt("A", unranked_choices())
    assert result.score_mode == "training"
    assert "rang" in result.score_reason.lower()
```

- [ ] **Step 2: Run scorer tests and confirm import failure.**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_practice_scoring.py -q`

Expected: FAIL because `backend.core.practice.scoring` does not exist.

- [ ] **Step 3: Implement the pure server scorer.**

Normalize responses and choices once. Reuse `compute_edn_score()` only when every scored proposition has a reliable rank. Otherwise calculate the existing discordance score, name it `training`, and construct deterministic proposition rows (selected, expected, rank, points, discordance).

- [ ] **Step 4: Replace duplicated `_same_closed_answer` calls in `save_attempt`.**

Save a single scored attempt, persist its proposition rows in the same request, and return its mode. Do not let the browser calculate points.

- [ ] **Step 5: Write and run persistence tests.**

```python
def test_saved_attempt_keeps_each_proposition_correction(practice_db):
    attempt_id = _save_ranked_answer()
    assert local_store.get_ai_practice_attempt_propositions(attempt_id) == [
        {"proposition_id": "A", "selected": 1, "expected": 1, "discordance": "correct", ...},
    ]
```

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_practice_scoring.py tests/test_ai_practice.py -q`

Expected: PASS.

- [ ] **Step 6: Display mode rather than an unqualified EDN note.**

For `training`, render exactly `Score d'entraînement non calibré EDN`; for `edn`, retain the EDN label. Render per-proposition discrepancy details from the API payload.

- [ ] **Step 7: Run Python and front-end tests.**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_practice_scoring.py tests/test_scoring_edn.py -q; npm test -- --run`

Expected: PASS.

### Task 4: Attribute evidence to questions and items (7.4)

**Files:**
- Modify: `backend/core/reviews/local_store.py`
- Modify: `backend/core/practice/mastery.py`
- Modify: `tests/test_ai_practice.py`
- Create: `tests/test_practice_question_items.py`

**Interfaces:**
- `set_ai_practice_question_items(question_id, links) -> None`.
- `get_ai_practice_session_item_scores(session_id) -> list[dict]` returns only question-linked, high-confidence item results.
- `record_ai_practice_mastery(session_id)` records one evaluation per attributable item, or none for legacy transverse sessions.

- [ ] **Step 1: Write failing attribution tests.**

```python
def test_transverse_session_scores_only_items_linked_to_its_questions(practice_db):
    session_id, cardio_question, diabetes_question = _transverse_session()
    set_ai_practice_question_items(cardio_question, [{"item_number": "221", "confidence": 1.0, "source": "manual"}])
    set_ai_practice_question_items(diabetes_question, [{"item_number": "245", "confidence": 1.0, "source": "manual"}])
    _answer(cardio_question, 100)
    _answer(diabetes_question, 0)
    assert get_ai_practice_session_item_scores(session_id) == [
        {"item_number": "221", "score_percent": 100.0},
        {"item_number": "245", "score_percent": 0.0},
    ]
```

- [ ] **Step 2: Run and confirm failure due to the absent question-item table/helper.**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_practice_question_items.py -q`

Expected: FAIL on the missing helper.

- [ ] **Step 3: Implement link read/write helpers and automatic primary-item links for new sessions.**

The helper validates `0 <= confidence <= 1`, accepts only declared sources, and uses `(question_id, item_number)` as the primary key. New generated/imported questions get their own primary item with confidence `1.0`; do not copy every session item to every question.

- [ ] **Step 4: Implement per-item aggregation and guarded mastery recording.**

Join last scored attempt per question to confident question-item links. A linked item gets its own average and question count. A legacy session with only `ai_practice_session_items` and no question links remains visible but yields no mastery evaluation.

- [ ] **Step 5: Run attribution and mastery regression tests.**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_practice_question_items.py tests/test_ai_practice.py tests/test_knowledge_mastery.py -q`

Expected: PASS.

### Task 5: Separate immediate performance from exposure and deduplicate retention (7.5, 7.6)

**Files:**
- Modify: `backend/core/reviews/mastery.py`
- Modify: `backend/core/reviews/local_store.py`
- Create: `tests/test_mastery_performance.py`
- Modify: `tests/test_knowledge_mastery.py`

**Interfaces:**
- `get_recent_qcm_performance(course_id, item_number) -> PerformanceSignal | None`.
- `_canonical_retention_evidence(...)` emits no more than one `Evidence` for a `(source, day)` group.
- `get_course_mastery(...)` reports a reason and next action for fresh low performance.

- [ ] **Step 1: Write tests for a fresh low result and same-day replay.**

```python
def test_recent_low_qcm_creates_a_performance_penalty(course, practice_db):
    _save_qcm(course, score_percent=25, total_questions=20, session_date="2026-08-03")
    snapshot = get_course_mastery(course)
    assert "QCM récent faible" in snapshot.reasons
    assert snapshot.next_action == "Corriger les erreurs"

def test_same_day_qcm_replays_are_aggregated_to_one_retention_evidence(course, practice_db):
    _save_qcm(course, score_percent=20, session_date="2026-08-03")
    _save_qcm(course, score_percent=95, session_date="2026-08-03")
    assert _retention_sources(get_course_mastery(course)) == [("qcm", date(2026, 8, 3))]
```

- [ ] **Step 2: Run the tests and confirm that a low fresh result currently has no direct penalty and duplicate evidence survives.**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_mastery_performance.py -q`

Expected: FAIL on both assertions.

- [ ] **Step 3: Implement an explicit recent-performance signal.**

Use completed QCM/DP/KFP results with `score_percent` and `total_questions`; weight confidence by question count and recency. Apply a bounded penalty only for a low-confidence-safe threshold (for example, 10+ questions and score below 50), append a human-readable reason, and select `Corriger les erreurs` as the next action.

- [ ] **Step 4: Canonicalize evidence before retention is calculated.**

Group candidates by source and business date, retain the conservative quality for the day, and prevent the same source/day from being added once through study sessions and again through canonical QCM rows. Persist prediction observations only after a future result resolves a prior prediction; do not alter historical timestamps.

- [ ] **Step 5: Run mastery and retention tests.**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_mastery_performance.py tests/test_knowledge_mastery.py tests/test_anki_evidence.py -q`

Expected: PASS.

### Task 6: Propagate one time zone through planning and Calendar (7.7)

**Files:**
- Modify: `frontend/components/course_quick_actions.py`
- Modify: `frontend/pages/planning_cockpit.py`
- Modify: `backend/core/google/calendar_service.py`
- Modify: `tests/test_consolidation.py`
- Create: `tests/test_calendar_timezone.py`

**Interfaces:**
- All business-date callers import `APP_TIMEZONE`, `now_local`, or `business_today` from `backend.config.settings`.
- Calendar event `start.timeZone` and `end.timeZone` equal `APP_TIMEZONE.key`.

- [ ] **Step 1: Write the failing Calendar payload test.**

```python
def test_google_event_uses_configured_business_timezone():
    body = calendar_service._event_body(_sample_event())
    assert body["start"]["timeZone"] == "Europe/Paris"
    assert body["end"]["timeZone"] == "Europe/Paris"
```

- [ ] **Step 2: Run it and confirm the hard-coded Reunion value fails.**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_calendar_timezone.py -q`

Expected: FAIL with `Indian/Reunion`.

- [ ] **Step 3: Replace local constants and date arithmetic.**

Import the settings functions in every identified caller; Calendar day ranges are created from local Paris midnight and serialized with `APP_TIMEZONE.key`. No module creates a `ZoneInfo("Indian/Reunion")` constant.

- [ ] **Step 4: Run all focused time-zone tests and search for forbidden hard coding.**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_app_timezone.py tests/test_calendar_timezone.py tests/test_consolidation.py tests/test_local_store.py -q; rg -n 'Indian/Reunion' backend frontend`

Expected: tests PASS; `rg` has no source-code hits.

### Task 7: Verify the end-to-end API and reader contract

**Files:**
- Modify: `tests/test_qcm_api_completion.py`
- Modify: the active React QCM tests under `frontend/react/qcm-app/`
- Modify: `docs/AUDIT_2026-08-03.md`

**Interfaces:**
- The complete endpoint returns either the stable completed payload or a 409 incomplete payload.
- Result screens label their score mode accurately and show stored proposition corrections.

- [ ] **Step 1: Add the end-to-end acceptance test.**

```python
def test_incorrect_complete_session_returns_correction_mode_and_one_mastery_record(client, practice_db):
    session_id = _ranked_session_with_one_incorrect_answer()
    first = client.post(f"/api/qcm/sessions/{session_id}/complete")
    second = client.post(f"/api/qcm/sessions/{session_id}/complete")
    assert first.status_code == second.status_code == 200
    assert first.json()["session"]["score_mode"] == "edn"
    assert first.json()["rows"][0]["propositions"]
    assert _mastery_record_count(session_id) == 1
```

- [ ] **Step 2: Run it first and confirm a failure is caused by a missing state/mode/proposition contract.**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_qcm_api_completion.py -q`

Expected: FAIL before the preceding tasks are complete.

- [ ] **Step 3: Adjust API/readers only to satisfy the established contract, then run focused regression suites.**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_ai_practice.py tests/test_practice_scoring.py tests/test_practice_question_items.py tests/test_mastery_performance.py tests/test_qcm_api_completion.py tests/test_app_timezone.py tests/test_calendar_timezone.py -q; npm test -- --run`

Expected: PASS.

- [ ] **Step 4: Run static integrity checks and document the audit status.**

Run: `.venv\\Scripts\\python.exe -m compileall backend frontend -q; git diff --check`

Expected: both commands exit 0. Update the existing audit under a separator with implemented behavior, migrations, focused test results, and any pre-existing suite failures that remain outside this lot.
