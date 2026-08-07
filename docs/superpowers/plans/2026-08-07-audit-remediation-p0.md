# Audit Remediation P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the four P0 correctness gaps identified by the 2026-08-07 Synapse audit.

**Architecture:** Keep the existing mastery, SQLite store, dashboard builder, and AI task boundaries. Add narrow helpers where behavior is currently implicit, then enforce each boundary with regression tests. Error signals are written from the QCM API after the scored attempt and keyed by attempt evidence so retries are idempotent.

**Tech Stack:** Python 3.11+, pytest, SQLite, NiceGUI, existing Gemini/AI service abstractions.

## Global Constraints

- Preserve the user-owned changes in `UNESS/.imported.json`, `docs/AUDIT_2026-08-07.md`, and `docs/SYNAPSE_AI_CONTEXT.md`.
- Do not call real Gemini, Notion, or Google APIs from tests.
- Follow red-green-refactor for every behavior change.
- Do not change the existing error-category vocabulary (`omission`, `exces`, and the existing zero-score reason).
- Missing frequency or availability data must use deterministic neutral fallbacks, never fabricated equal values.

---

### Task 1: Guard Rang A level classification

**Files:**
- Modify: `backend/core/reviews/mastery.py:276-285`
- Test: `tests/test_knowledge_mastery.py`

**Interfaces:**
- Consumes: `_has_rang_a_evidence` and `score_rang_a` already calculated by `get_course_mastery`.
- Produces: existing `CourseProgressSnapshot` shape, with Rang A threshold reasons only when evidence exists.

- [ ] **Step 1: Write the failing regression test**

Add a test with a declared course whose calculated score is between 60 and 75 and no `lisa_oic` rows. Assert that the snapshot is not classified as `fragile` solely by the Rang A threshold and that no `Sécurité Rang A non atteinte` reason is present.

- [ ] **Step 2: Run the focused test**

Run: `python -m pytest tests/test_knowledge_mastery.py -k rang_a -q`

Expected: the new test fails because the current level condition applies `score_rang_a < 75` without checking evidence.

- [ ] **Step 3: Implement the minimal guard**

Change both level threshold expressions and the related reason branch so the Rang A terms are included only when `_has_rang_a_evidence` is true. Preserve the existing score fields for UI compatibility.

- [ ] **Step 4: Run the focused and regression tests**

Run: `python -m pytest tests/test_knowledge_mastery.py -q`

Expected: PASS with all existing mastery behavior preserved.

- [ ] **Step 5: Commit**

Run: `git add tests/test_knowledge_mastery.py backend/core/reviews/mastery.py && git commit -m "fix: gate mastery level on Rang A evidence"`

### Task 2: Persist idempotent QCM error signals

**Files:**
- Modify: `backend/core/reviews/local_store.py:343-354,803-817`
- Modify: `backend/api/qcm.py:155-174`
- Test: `tests/test_error_signal_ingestion.py`

**Interfaces:**
- Consumes: scored propositions from `score_closed_attempt`, item links from `ai_practice_question_items`, and the persisted attempt ID.
- Produces: one `error_signals` row per `(attempt_id, item_number, category)` with `evidence_id` equal to the attempt ID.

- [ ] **Step 1: Write the failing tests**

Create `test_incorrect_linked_attempt_writes_error_signals` and `test_reingesting_attempt_is_idempotent`. The first creates an isolated QCM session, links its question to item `221`, posts an incorrect answer through `save_attempt`, and asserts that `get_error_signals(item_number="221")` contains the expected `omission`/`exces` categories. The second invokes the same ingestion helper twice with the same attempt ID and asserts that the signal count is unchanged.

- [ ] **Step 2: Run the focused tests**

Run: `python -m pytest tests/test_error_signal_ingestion.py -q`

Expected: FAIL because `save_attempt` currently persists propositions but never writes `error_signals`.

- [ ] **Step 3: Add an idempotent store operation**

Add a unique index or an `INSERT ... WHERE NOT EXISTS` guard for `(source, evidence_id, item_number, category)`, and add a small helper that inserts a signal only when that identity is absent.

- [ ] **Step 4: Connect the QCM API flow**

After the attempt and propositions are persisted, query the question's linked items and insert signals for proposition rows whose `discordance` is not `correct`. Use the existing category values and the attempt ID as evidence. Do not create signals for open questions or unlinked questions.

- [ ] **Step 5: Run focused and practice tests**

Run: `python -m pytest tests/test_error_signal_ingestion.py tests/test_ai_practice.py tests/test_error_profile.py -q`

Expected: PASS and no duplicate signal rows.

- [ ] **Step 6: Commit**

Run: `git add backend/core/reviews/local_store.py backend/api/qcm.py tests/test_error_signal_ingestion.py && git commit -m "feat: record adaptive practice error signals"`

### Task 3: Replace dashboard F3 constants with local data

**Files:**
- Modify: `frontend/pages/dashboard/_cockpit_today.py:53-91`
- Test: `tests/test_edn_gain_priority.py`

**Interfaces:**
- Consumes: `local_store.get_ednpro_item_frequency`, the local AI-practice question catalog, and existing mastery/error inputs.
- Produces: the same item dictionaries consumed by `rank_gain_potential`, with real `edn_weight` and `available_questions` values.

- [ ] **Step 1: Write failing tests**

Add one test proving two items with different stored frequencies produce different `edn_weight` values, and one test proving question availability comes from stored questions rather than the constant `10`.

- [ ] **Step 2: Run focused tests**

Run: `python -m pytest tests/test_edn_gain_priority.py -q`

Expected: FAIL because `build_gain_items` currently emits `0.7` and `10` for every item.

- [ ] **Step 3: Implement narrow local lookups**

Use the existing frequency accessor and a single local query/helper for question count. Normalize the frequency into the `[0, 1]` range expected by `rank_gain_potential`; use `0.5` for missing weight and `0` for missing question availability.

- [ ] **Step 4: Verify ranking and existing dashboard tests**

Run: `python -m pytest tests/test_edn_gain_priority.py tests/test_cockpit_today_session_feedback.py tests/test_cockpit_shell.py -q`

Expected: PASS with deterministic fallback behavior.

- [ ] **Step 5: Commit**

Run: `git add frontend/pages/dashboard/_cockpit_today.py tests/test_edn_gain_priority.py && git commit -m "fix: use local data for dashboard gain priority"`

### Task 4: Enforce the UNESS human-validation status

**Files:**
- Modify: `backend/core/ai/tasks.py:53-104`
- Modify: `backend/core/ednpro/ai_pipeline.py:160-190` and `backend/core/uness/gemini_autocorrect.py:190-220` only if their callers require the status.
- Test: `tests/test_ai_tasks.py` and the relevant UNESS correction tests.

**Interfaces:**
- Consumes: `generate_uness_correction` responses and the existing `GridExtractionResult` validation marker.
- Produces: an explicit pending-human-validation status for visual corrections; no caller may treat it as final by default.

- [ ] **Step 1: Write the failing production-path test**

Call `generate_uness_correction` with images and assert that the returned result exposes a pending validation status, while the text-only correction remains automatically usable.

- [ ] **Step 2: Run the focused test**

Run: `python -m pytest tests/test_ai_tasks.py -q`

Expected: FAIL because `generate_uness_correction` currently returns a raw `AIResponse` without a validation status.

- [ ] **Step 3: Add the smallest explicit status contract**

Wrap the response in a small immutable result carrying `response`, `requires_human_validation`, and `status`, or extend the existing result type if callers already support that shape. Set the status only for visual corrections and update both production callers to preserve it.

- [ ] **Step 4: Verify caller compatibility**

Run: `python -m pytest tests/test_ai_tasks.py tests/test_uness_correction_failures.py tests/test_ednpro_pipeline.py -q`

Expected: PASS without changing the model routing.

- [ ] **Step 5: Commit**

Run: `git add backend/core/ai/tasks.py backend/core/ednpro/ai_pipeline.py backend/core/uness/gemini_autocorrect.py tests/test_ai_tasks.py tests/test_uness_correction_failures.py tests/test_ednpro_pipeline.py && git commit -m "fix: require human validation for visual UNESS corrections"`

### Task 5: P0 verification

**Files:**
- No production files; inspect the commits and test output.

- [ ] **Step 1: Run the P0 regression suite**

Run: `python -m pytest tests/test_knowledge_mastery.py tests/test_error_profile.py tests/test_error_signal_ingestion.py tests/test_edn_gain_priority.py tests/test_ai_tasks.py tests/test_uness_correction_failures.py tests/test_ednpro_pipeline.py -q`

Expected: all selected tests pass without API calls.

- [ ] **Step 2: Run lint on changed Python files**

Run: `ruff check backend/core/reviews/mastery.py backend/core/reviews/local_store.py backend/api/qcm.py backend/core/ai/tasks.py backend/core/ednpro/ai_pipeline.py backend/core/uness/gemini_autocorrect.py frontend/pages/dashboard/_cockpit_today.py`

Expected: no new lint errors.

- [ ] **Step 3: Inspect the working tree**

Run: `git status --short`

Expected: only the known user-owned files remain uncommitted; P0 implementation files are committed.
