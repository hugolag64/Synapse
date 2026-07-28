# Adaptive Mastery Decay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the displayed mastery score and its prediction curve use one adaptive, date-aware retention model.

**Architecture:** Add a pure retention module that turns dated evidence into a current score and stability. Keep the existing evidence/base-score rules in `mastery.py`, then apply retention once at the end. Make the SVG curve call the same pure projection function rather than maintaining a second decay formula.

**Tech Stack:** Python 3, dataclasses, existing SQLite rows, pytest, NiceGUI SVG component.

## Global Constraints

- The mastery floor is 25 and the score remains bounded between 0 and 100.
- Reading alone is weak evidence; objective EDN evaluations and Anki outcomes are stronger evidence.
- Historical evidence uses its recorded session/review date.
- Anki’s scheduler remains authoritative for card scheduling; Synapse only consumes its outcomes.
- Existing database rows remain readable without migration when a date is missing.

---

### Task 1: Pure adaptive retention model

**Files:**
- Create: `backend/core/knowledge/retention.py`
- Test: `tests/test_knowledge_retention.py`

**Interfaces:**
- `Evidence(date: datetime.date, source: str, quality: float)` dataclass.
- `RetentionSnapshot(score: int, stability_days: float, last_evidence: datetime.date | None)` dataclass.
- `evaluate_retention(base_score: int, evidence: Sequence[Evidence], as_of: datetime.date) -> RetentionSnapshot`.
- `project_retention(score: int, stability_days: float, days: float) -> float`.

- [ ] **Step 1: Write failing tests**

```python
def test_score_declines_with_age_but_not_to_zero():
    from backend.core.knowledge.retention import Evidence, evaluate_retention
    today = datetime.date(2026, 7, 28)
    result = evaluate_retention(80, [Evidence(today - datetime.timedelta(days=90), "lecture", .5)], today)
    assert 25 < result.score < 80

def test_successful_repeated_evidence_creates_more_stability_than_one_reading():
    from backend.core.knowledge.retention import Evidence, evaluate_retention
    today = datetime.date(2026, 7, 28)
    one = [Evidence(today - datetime.timedelta(days=60), "lecture", .5)]
    repeated = [Evidence(today - datetime.timedelta(days=60), "lecture", .5),
                Evidence(today - datetime.timedelta(days=30), "qcm", .9),
                Evidence(today, "anki", .9)]
    assert evaluate_retention(80, repeated, today).stability_days > evaluate_retention(80, one, today).stability_days

def test_low_quality_evidence_reduces_stability():
    from backend.core.knowledge.retention import Evidence, evaluate_retention
    today = datetime.date(2026, 7, 28)
    good = [Evidence(today - datetime.timedelta(days=30), "qcm", .9)]
    weak = [Evidence(today - datetime.timedelta(days=30), "qcm", .2)]
    assert evaluate_retention(80, weak, today).stability_days < evaluate_retention(80, good, today).stability_days

def test_current_evidence_resets_age():
    from backend.core.knowledge.retention import Evidence, evaluate_retention
    today = datetime.date(2026, 7, 28)
    result = evaluate_retention(80, [Evidence(today, "qcm", .9)], today)
    assert result.last_evidence == today
    assert result.score == 80
```

- [ ] **Step 2: Run the focused tests and verify they fail for the missing module**

Run: `pytest tests/test_knowledge_retention.py -q`

Expected: collection failure because `backend.core.knowledge.retention` does not exist.

- [ ] **Step 3: Implement the minimal pure model**

Use source base stabilities of 7 days for lectures, 14 for manual/confidence evidence, 21 for QCM/DP/KFP/OIC, and 14 for Anki. Apply quality-aware multiplicative growth or contraction, cap stability at 730 days, and project toward `MASTERY_FLOOR = 25` with `2 ** (-age / stability)`.

- [ ] **Step 4: Run the focused tests**

Run: `pytest tests/test_knowledge_retention.py -q`

Expected: all retention tests pass.

- [ ] **Step 5: Commit the isolated model**

```powershell
git add tests/test_knowledge_retention.py backend/core/knowledge/retention.py
git commit -m "feat: add adaptive mastery retention model"
```

### Task 2: Feed real evidence into mastery

**Files:**
- Modify: `backend/core/reviews/mastery.py`
- Test: `tests/test_knowledge_mastery.py`

**Interfaces:**
- Preserve `get_course_mastery(course, context="college", sessions=None, total_postpone=0, qcm_done_local=False) -> CourseProgressSnapshot`.
- Add a private adapter that converts sessions and Anki evidence rows into `Evidence` values using `session_date`, Anki review date, activity type, confidence, QCM result, and difficulty.

- [ ] **Step 1: Add failing mastery integration tests**

```python
def test_manual_revision_date_changes_current_mastery():
    import backend.core.reviews.local_store as ls
    today = datetime.date(2026, 7, 28)
    course = _course(first_read=today, nb_lectures=1)
    old = [{"session_date": "2026-04-29", "confidence": 4,
            "difficulty": "facile", "qcm_result": "réussi"}]
    current = [{"session_date": "2026-07-28", "confidence": 4,
                "difficulty": "facile", "qcm_result": "réussi"}]
    assert get_course_mastery(course, sessions=current).score > get_course_mastery(course, sessions=old).score

def test_good_qcm_and_anki_evidence_stabilize_more_than_a_single_reading():
    today = datetime.date(2026, 7, 28)
    course = _course(first_read=today - datetime.timedelta(days=90), nb_lectures=1)
    reading = [{"session_date": "2026-04-29", "confidence": 2,
                "difficulty": "moyen", "qcm_result": None}]
    repeated = [
        {"session_date": "2026-04-29", "confidence": 2, "difficulty": "moyen", "qcm_result": None},
        {"session_date": "2026-05-29", "confidence": 4, "difficulty": "facile", "qcm_result": "réussi"},
        {"session_date": "2026-07-28", "confidence": 4, "difficulty": "facile", "qcm_result": "réussi"},
    ]
    assert get_course_mastery(course, sessions=repeated).score > get_course_mastery(course, sessions=reading).score
```

- [ ] **Step 2: Run the focused tests and verify the expected failures**

Run: `pytest tests/test_knowledge_mastery.py -q`

Expected: the new assertions fail because the current score ignores evidence age and stability.

- [ ] **Step 3: Implement the evidence adapter and apply retention once**

Keep the existing score calculation and seed/Anki blending as the base score. Build dated evidence from sessions and Anki rows, calculate `evaluate_retention(base_score, evidence, today)`, replace the returned score with the snapshot score, and append a concise reason when the score is decayed. Preserve all early “not started” branches.

- [ ] **Step 4: Run mastery and regression tests**

Run: `pytest tests/test_knowledge_mastery.py tests/test_manual_review.py tests/test_anki_evidence.py -q`

Expected: all focused tests pass; existing seed and Anki semantics remain intact.

- [ ] **Step 5: Commit the mastery integration**

```powershell
git add tests/test_knowledge_mastery.py backend/core/reviews/mastery.py
git commit -m "feat: apply dated evidence to mastery score"
```

### Task 3: Make the prediction graph use the same model

**Files:**
- Modify: `frontend/components/forgetting_curve.py`
- Modify: `frontend/pages/course_detail_cockpit.py` only if the snapshot needs stability exposed.
- Test: `tests/test_forgetting_curve.py`

**Interfaces:**
- Preserve `project_score(score0, days, interval_d)` for callers, but route it through the shared retention projection with the snapshot stability when available.
- Preserve the current SVG labels and “sans révision” semantics.

- [ ] **Step 1: Write failing curve tests**

```python
def test_project_score_uses_adaptive_stability():
    from frontend.components.forgetting_curve import project_score
    assert project_score(80, 60, 120) > project_score(80, 60, 7)
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `pytest tests/test_forgetting_curve.py -q`

Expected: failure because the current function clamps stability to the review-cycle interval and does not accept adaptive stability.

- [ ] **Step 3: Connect the graph to the shared projection**

Pass the retention stability from the mastery snapshot when rendering the item cockpit. Keep the old interval fallback for screens without a mastery snapshot and use the shared floor/constants.

- [ ] **Step 4: Run focused UI/component tests**

Run: `pytest tests/test_forgetting_curve.py tests/test_course_detail_oic_tab.py tests/test_manual_review.py -q`

Expected: all pass.

- [ ] **Step 5: Commit the graph integration**

```powershell
git add tests/test_forgetting_curve.py frontend/components/forgetting_curve.py frontend/pages/course_detail_cockpit.py
git commit -m "feat: align mastery prediction with retention model"
```

### Task 4: Full verification and documentation

**Files:**
- Modify: `docs/PROGRESSION_SESSION_2026-07-28.md` with the implemented algorithm and test result.

- [ ] **Step 1: Run the complete test suite**

Run: `pytest -q`

Expected: all tests pass with no new warnings or errors.

- [ ] **Step 2: Inspect the final diff and run syntax checks**

Run: `git diff --check; python -m compileall backend frontend tests -q`

Expected: no whitespace errors and successful compilation.

- [ ] **Step 3: Update the session progression note**

Record the adaptive-stability behavior, the shared graph/score calculation, and the exact verification command/result.

- [ ] **Step 4: Commit the verified integration**

```powershell
git add docs/PROGRESSION_SESSION_2026-07-28.md
git commit -m "docs: record adaptive mastery integration"
```
