# QCM Result Versioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist immutable initial and final versions of every QCM evaluation while keeping `qcm_sessions` as the current compatibility view.

**Architecture:** Add an append-only `qcm_result_versions` table and a migration in `local_store`. Create the initial snapshot during `add_qcm_session_full()` and expose an atomic finalization helper that updates the current row plus appends a final revision. Add focused store tests and update the audit follow-up.

**Tech Stack:** Python 3.11+, SQLite, pytest, existing `local_store` connection helper.

## Global Constraints

- Never delete or mutate an existing result snapshot.
- Never store API keys or raw secrets in snapshot metadata.
- Preserve the existing `qcm_sessions` read path and APIs.
- Final snapshots require non-empty provenance and reason.

---

### Task 1: Persist result snapshots

**Files:**
- Modify: `backend/core/reviews/local_store.py`
- Test: `tests/test_qcm_result_versions.py`

**Interfaces:**
- Produce `record_qcm_result_final(session_id: int, *, source: str, reason: str, ... ) -> int`.
- Produce `list_qcm_result_versions(session_id: int) -> list[dict]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_new_qcm_session_creates_initial_snapshot():
    session_id = local_store.add_qcm_session_full(
        platform="Synapse IA", session_date="2026-08-16", item_number="230",
        score_percent=66.67, total_questions=3, correct_answers=2,
        wrong_answers=1, rank_a_questions=2, rank_a_correct=1,
    )
    versions = local_store.list_qcm_result_versions(session_id)
    assert [(row["phase"], row["revision"]) for row in versions] == [("initial", 1)]
    assert versions[0]["score_percent"] == 66.67


def test_final_snapshot_is_append_only_and_becomes_current_result():
    session_id = local_store.add_qcm_session_full(
        platform="Synapse IA", session_date="2026-08-16", score_percent=50,
        total_questions=2, correct_answers=1, wrong_answers=1,
    )
    version_id = local_store.record_qcm_result_final(
        session_id, source="official_data", reason="Rang officiel reçu",
        score_percent=100, total_questions=2, correct_answers=2,
        wrong_answers=0, rank_a_questions=2, rank_a_correct=2,
    )
    assert version_id > 0
    versions = local_store.list_qcm_result_versions(session_id)
    assert [row["phase"] for row in versions] == ["initial", "final"]
    assert versions[0]["score_percent"] == 50
    assert versions[1]["score_percent"] == 100
    assert local_store.get_qcm_sessions_all(limit=1)[0]["score_percent"] == 100


def test_second_final_snapshot_gets_next_revision_and_invalid_input_is_atomic():
    session_id = local_store.add_qcm_session_full(
        platform="Synapse IA", session_date="2026-08-16", score_percent=50,
    )
    local_store.record_qcm_result_final(
        session_id, source="official_data", reason="Première correction", score_percent=60,
    )
    local_store.record_qcm_result_final(
        session_id, source="admin", reason="Correction confirmée", score_percent=70,
    )
    assert [row["revision"] for row in local_store.list_qcm_result_versions(session_id)] == [1, 1, 2]
    with pytest.raises(ValueError):
        local_store.record_qcm_result_final(session_id, source="", reason="", score_percent=0)
    assert len(local_store.list_qcm_result_versions(session_id)) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_qcm_result_versions.py -q`

Expected: FAIL because the snapshot table and public functions do not exist.

- [ ] **Step 3: Implement the migration and atomic helpers**

Add `_migrate_qcm_result_versions()` to the existing initialization sequence. Add the append-only table with a foreign key to `qcm_sessions`, phase/revision constraints, all score/rank fields, `source`, `reason`, `scoring_version`, `metadata_json`, and `created_at`. Call a private insert helper from `add_qcm_session_full()` before committing the transaction. Implement `record_qcm_result_final()` with input validation, one transaction for updating `qcm_sessions` and inserting the next final revision, and `list_qcm_result_versions()` ordered by phase/revision.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_qcm_result_versions.py tests/test_evaluation_service.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/core/reviews/local_store.py tests/test_qcm_result_versions.py
git commit -m "feat: version qcm result snapshots"
```

### Task 2: Wire audit documentation and regression verification

**Files:**
- Modify: `docs/AUDIT_QCM_ANNALES_2026-08-15_SUIVI.md`
- Test: `tests/test_qcm_result_versions.py`

- [ ] **Step 1: Add migration and compatibility assertions**

Assert that a fresh temporary database creates the table through `init_db()` and that legacy `qcm_sessions` reads remain unchanged.

- [ ] **Step 2: Run the focused regression suite**

Run: `pytest tests/test_qcm_result_versions.py tests/test_qcm_api.py tests/test_qcm_api_completion.py tests/test_practice_mastery.py -q`

Expected: all focused tests pass.

- [ ] **Step 3: Mark the audit item delivered**

Add the snapshot behavior to the delivered section and remove it from the remaining list, preserving the four unrelated remaining audit items.

- [ ] **Step 4: Run repository verification**

Run: `python -m compileall -q backend` and `git diff --check`.

- [ ] **Step 5: Commit**

```bash
git add docs/AUDIT_QCM_ANNALES_2026-08-15_SUIVI.md tests/test_qcm_result_versions.py
git commit -m "docs: close qcm result versioning audit item"
```
