# Official Exam Composition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build deterministic server-side official exam compositions from imported UNESS questions and open them in the active React reader with server-enforced order.

**Architecture:** Add an `exam_compositions` persistence table and session metadata for exam mode. Implement a pure-ish composer that loads UNESS candidates, scores them from local frequency/error/recency signals, and selects by a seeded RNG. Wire the existing NiceGUI setup page to the composer and enforce sequential attempts in the QCM API/store.

**Tech Stack:** Python 3.11+, SQLite, FastAPI, NiceGUI, React/Vite, pytest.

## Global Constraints

- No Gemini or network call is made during composition.
- The seed and ordered question IDs are persisted before the reader opens.
- Official exam mode never exposes rank badges during answering.
- Existing non-exam sessions keep their current behavior.
- A missing candidate pool fails explicitly; it never silently falls back to random data.

---

### Task 1: Persist candidate composition and exam session metadata

**Files:**
- Modify: `backend/core/reviews/local_store.py`
- Test: `tests/test_exam_composition.py`

**Interfaces:**
- Produce `create_ai_practice_session(..., exam_mode=False, exam_format="", exam_seed="", duration_seconds=None) -> int`.
- Produce `save_exam_composition(session_id, *, format, seed, duration_seconds, question_ids) -> int`.
- Produce `get_exam_composition(session_id) -> dict | None`.

- [ ] **Step 1: Write failing migration/session tests**

```python
def test_exam_session_persists_mode_duration_and_composition(isolated_db):
    session_id = local_store.create_ai_practice_session(
        spec=_spec(total_questions=2),
        questions=[_question("q1"), _question("q2")],
        model="exam-composer-v1",
        exam_mode=True,
        exam_format="series",
        exam_seed="seed-1",
        duration_seconds=5400,
    )
    local_store.save_exam_composition(
        session_id, format="series", seed="seed-1", duration_seconds=5400,
        question_ids=[1, 2],
    )
    session = local_store.get_ai_practice_session_summary(session_id)
    composition = local_store.get_exam_composition(session_id)
    assert session["exam_mode"] == 1
    assert session["duration_seconds"] == 5400
    assert composition["seed"] == "seed-1"
    assert composition["question_ids"] == [1, 2]
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest tests/test_exam_composition.py -q`

Expected: FAIL because the migration columns and composition table do not exist.

- [ ] **Step 3: Implement the migration and persistence helpers**

Add idempotent columns `exam_mode`, `exam_format`, `exam_seed`, and
`duration_seconds` to `ai_practice_sessions`. Add `exam_compositions` with a
unique `session_id`, format check, seed, duration, ordered question IDs JSON,
selection policy and creation time. Extend `create_ai_practice_session()` and
return decoded composition metadata from `get_exam_composition()`.

- [ ] **Step 4: Run the tests to verify green**

Run: `pytest tests/test_exam_composition.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/reviews/local_store.py tests/test_exam_composition.py
git commit -m "feat: persist official exam composition metadata"
```

### Task 2: Implement deterministic weighted composition

**Files:**
- Create: `backend/core/uness/exam_composer.py`
- Modify: `backend/core/reviews/local_store.py`
- Test: `tests/test_exam_composer.py`

**Interfaces:**
- Produce `ExamFormat = Literal["dp", "series", "mixed"]`.
- Produce `compose_exam_session(*, format: ExamFormat, subject: str | None = None, seed: str, duration_seconds: int | None = None) -> dict`.

- [ ] **Step 1: Write failing selection tests**

```python
def test_same_seed_reproduces_the_same_composition(isolated_db):
    _seed_uness_questions(isolated_db)
    first = compose_exam_session(format="series", seed="abc", question_count=4)
    second = compose_exam_session(format="series", seed="abc", question_count=4)
    assert first["question_ids"] == second["question_ids"]
    assert first["seed"] == "abc"


def test_formats_respect_cardinality_and_deduplicate_questions(isolated_db):
    _seed_uness_questions(isolated_db)
    dp = compose_exam_session(format="dp", seed="dp-seed", dp_count=3)
    series = compose_exam_session(format="series", seed="series-seed", question_count=5)
    mixed = compose_exam_session(format="mixed", seed="mixed-seed", dp_count=2, question_count=4)
    assert len(dp["session_ids"]) == 3
    assert len(series["question_ids"]) == 5
    assert len(mixed["question_ids"]) == len(set(mixed["question_ids"]))


def test_composer_rejects_insufficient_candidates(isolated_db):
    with pytest.raises(ValueError, match="candidats"):
        compose_exam_session(format="series", seed="empty", question_count=5)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_exam_composer.py -q`

Expected: FAIL because `exam_composer` does not exist.

- [ ] **Step 3: Implement candidate loading and weighted seeded selection**

Load only UNESS-linked questions/sessions. Derive candidate weights from
`ednpro_item_frequency`, `error_signals`, and the latest `qcm_sessions` date;
normalize each factor to a bounded positive weight. Use `random.Random(seed)`
for weighted sampling without replacement. For `dp`, select distinct sessions
with at least two questions; for `series`, select questions from distinct
sessions; for `mixed`, combine distinct DP sessions with isolated questions.
Create the `ai_practice` session in the selected order, persist the composition,
and return session ID, seed, format, duration, question IDs, and source session IDs.

- [ ] **Step 4: Run tests to verify green**

Run: `pytest tests/test_exam_composer.py tests/test_exam_composition.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/uness/exam_composer.py backend/core/reviews/local_store.py tests/test_exam_composer.py
git commit -m "feat: compose deterministic official exams"
```

### Task 3: Enforce exam order and wire the active reader flow

**Files:**
- Modify: `backend/core/reviews/local_store.py`
- Modify: `backend/api/qcm.py`
- Modify: `frontend/pages/exam_simulator_page.py`
- Test: `tests/test_exam_composition.py`

- [ ] **Step 1: Write failing order tests**

```python
def test_exam_session_rejects_out_of_order_attempts(isolated_db):
    session_id, first_id, second_id = _exam_session(isolated_db)
    with pytest.raises(ValueError, match="ordre"):
        local_store.record_ai_practice_attempt(
            session_id=session_id, question_id=second_id, response="A",
            score_percent=0, is_correct=False,
        )
    local_store.record_ai_practice_attempt(
        session_id=session_id, question_id=first_id, response="A",
        score_percent=100, is_correct=True,
    )
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_exam_composition.py::test_exam_session_rejects_out_of_order_attempts -q`

Expected: FAIL because exam sessions currently accept any question order.

- [ ] **Step 3: Implement server guard and page wiring**

Before inserting a normal exam attempt, compare the submitted question position
with the first unanswered position in `ai_practice_session_questions`. Permit
`score_mode="timed_out"` for the timeout completion loop. Map the guard to HTTP
400 in `save_attempt()`. Replace `_start_exam()` in the configuration page with
`compose_exam_session()` and navigate to `/qcm-app/?session=<id>&exam=1&duration=<seconds>`.
Keep the legacy debrief code unreachable but do not change scoring behavior for
non-exam sessions.

- [ ] **Step 4: Run focused verification**

Run: `pytest tests/test_exam_composition.py tests/test_exam_composer.py tests/test_exam_session.py -q`

Expected: PASS.

- [ ] **Step 5: Update audit and commit**

Mark the composition item delivered in
`docs/AUDIT_QCM_ANNALES_2026-08-15_SUIVI.md`, then run
`python -m compileall -q backend`, `git diff --check`, and commit:

```bash
git add backend/api/qcm.py frontend/pages/exam_simulator_page.py docs/AUDIT_QCM_ANNALES_2026-08-15_SUIVI.md tests/test_exam_composition.py
git commit -m "feat: open deterministic exams in the react reader"
```
