# Audit QCM / Annales — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the QCM/annales pipeline, scoring, mastery, timing, correction UI and safety controls with the validated R2C/CNG rules and the decisions recorded during the audit review.

**Architecture:** Keep official data authoritative and deterministic. Normalize source formats into a canonical model, preserve raw provenance, and treat Gemini only as a traceable fallback for rank inference or pedagogical explanation. React remains the only canonical question reader; legacy NiceGUI routes redirect to it.

**Tech Stack:** Python 3.11+, Pydantic, SQLite, FastAPI/NiceGUI backend, React/TypeScript reader, pytest.

## Global Constraints

- Official correction data is authoritative; AI/manual pedagogical text never changes the official score.
- Missing or contradictory official format/correction/rank data produces a preserved but non-noted question.
- Official source rank outranks Gemini; Gemini high-confidence inference outranks manual admin correction; unknown remains unknown.
- No raw API key, prompt header, or secret may be persisted in logs or backups.
- Completed results are versioned, never silently overwritten; open sessions may be finalized when pending data becomes reliable.
- Every new behavior is covered by a failing test before production code.

### Task 1: Canonical official formats and authoritative scoring

**Files:**
- Modify: `backend/core/practice/scoring.py`
- Modify: `backend/core/practice/attempt_service.py`
- Modify: `backend/core/uness/models.py`
- Modify: `backend/core/uness/import_service.py`
- Test: `tests/test_practice_scoring.py`
- Test: `tests/test_uness_import.py`

- [ ] Add golden tests for QRU, QRM, QRP, QRP long, QZP, QROC and TCS, including missing/invalid official data.
- [ ] Run the focused tests and confirm the new cases fail for the current implementation.
- [ ] Add canonical format normalization while preserving the raw source type.
- [ ] Read nested UNESS type metadata instead of defaulting every closed question to QRM.
- [ ] Make `None` official answers distinct from false answers and exclude malformed official corrections from scoring/mastery.
- [ ] Carry rank, rank source, confidence, indispensable and inacceptable metadata through import models.
- [ ] Keep full precision internally, apply the 14/20 Rang A threshold before display rounding, and store the scoring-engine version.
- [ ] Run the focused scoring/import suite.

### Task 2: Rank inference and provenance

**Files:**
- Modify: `backend/core/ednpro/rank_inference.py`
- Modify: `backend/core/ednpro/qcm_capture.py`
- Modify: `backend/core/ai/logger.py`
- Add: `backend/core/practice/rank_service.py`
- Test: `tests/test_rank_inference.py`

- [ ] Add tests for official > Gemini >= 0.85 > admin fallback > unknown precedence, ambiguity rejection, and question-level validation.
- [ ] Run them red.
- [ ] Implement asynchronous, grouped-per-item Gemini inference with OIC context, strict schema validation, max three total attempts and relaunchable failures.
- [ ] Persist model, prompt version, OIC input, raw structured response, confidence, rationale, source and audit timestamps.
- [ ] Add cost estimation/guard hooks using the configured model and a 5 EUR per-import default limit.
- [ ] Run focused tests and lint.

### Task 3: Mastery, replay and result versioning

**Files:**
- Modify: `backend/core/practice/mastery.py`
- Modify: `backend/core/practice/attempt_service.py`
- Modify: `backend/core/practice/models.py`
- Test: `tests/test_mastery.py`
- Test: `tests/test_attempt_service.py`

- [ ] Add tests for course-less QCM/DP/KFP evidence, multi-item `1/n` weighting, non-noted exclusion, first exposure versus replay, and open-session finalization.
- [ ] Run them red.
- [ ] Remove the inappropriate course guard for QCM/DP/KFP while retaining OIC-course requirements where needed.
- [ ] Store stable question/version references and separate retention metrics from primary mastery.
- [ ] Create immutable initial/final result versions instead of overwriting completed attempts.
- [ ] Run focused mastery tests.

### Task 4: Import safety, images and retries

**Files:**
- Modify: `backend/core/ai/tasks.py`
- Modify: `backend/core/uness/gemini_autocorrect.py`
- Modify: `backend/core/uness/import_service.py`
- Add: `backend/core/ai/retry_policy.py`
- Test: `tests/test_gemini_autocorrect.py`
- Test: `tests/test_import_pipeline.py`

- [ ] Add tests proving visual questions import when an image exists, remain pending for explanation, and are not published when required image data is missing.
- [ ] Add tests for exact stable-ID matching, ambiguous title mismatch rejection, partial batch retry and publication only after complete validation.
- [ ] Run them red.
- [ ] Implement centralized retry/backoff/Retry-After handling and relaunchable failure states.
- [ ] Make import publication atomic per annale while preserving raw artifacts and question-level partial status.
- [ ] Prohibit unsafe sanitization bypasses for UNESS/Gemini/base content.
- [ ] Run focused import tests.

### Task 5: Timed sessions and authoritative API behavior

**Files:**
- Modify: `backend/api/qcm.py`
- Modify: `backend/core/practice/service.py`
- Modify: `frontend/pages/qcm_cockpit.py`
- Modify: `frontend/pages/annale_detail.py`
- Modify: `frontend/components/practice_session_card.py`
- Test: `tests/test_qcm_api.py`

- [ ] Add tests for correction-mode propagation, immutable correction sessions, official duration precedence, elapsed-time persistence, timeout submission and practice/exam mastery mode.
- [ ] Run them red.
- [ ] Centralize route construction so `/qcm` and `/annales` always preserve `correction=1`.
- [ ] Implement official global durations (EDN 3h, LCA 1h30), optional annale duration, free practice by default, and backend-authoritative timeout handling.
- [ ] Freeze question versions and scoring rules at session start.
- [ ] Run focused API tests.

### Task 6: React canonical reader and result UX

**Files:**
- Modify: `qcm_app/src/main.tsx`
- Modify: `qcm_app/src/api.ts`
- Modify: `qcm_app/src/types.ts`
- Modify: `frontend/pages/annales.py`
- Modify: `frontend/pages/exam_simulator_page.py`
- Test: `qcm_app/src/*.test.tsx`

- [ ] Add tests for rank pills, official-versus-inferred provenance, hidden rank during composition, revealed rank in debrief, non-noted states, global timer expiry, and no generic PASSÉ/LIMITE/RATÉ labels.
- [ ] Run them red.
- [ ] Make React the only reader, keeping legacy routes as redirects during migration.
- [ ] Add rank/status/correction layers and explicit result states (`noted`, `provisional`, `not calculable`).
- [ ] Replace 120-second-per-question logic with global mode duration and auto-submit/lock on expiry.
- [ ] Show `/qcm` as the home with “À travailler aujourd’hui” and “Composer une épreuve”; preserve official annale order/DP blocks and expose partial mode explicitly.
- [ ] Run frontend tests/build.

### Task 7: Recommendations, archive and operations

**Files:**
- Modify: `frontend/pages/qcm_cockpit.py`
- Modify: `frontend/pages/annales.py`
- Modify: `backend/core/practice/recommendations.py`
- Add: `backend/core/ops/backup_service.py`
- Test: `tests/test_recommendations.py`
- Test: `tests/test_backup_service.py`

- [ ] Add tests for deterministic “À travailler demain”, Anti-Biais only in generated training, frozen selection seed, archive behavior and backup verification.
- [ ] Run them red.
- [ ] Exclude non-noted/unknown questions from recommendations and keep official annales unmodified.
- [ ] Implement archive/restore semantics and explicit permanent deletion protection.
- [ ] Add encrypted daily/weekly local backups, second-volume copy, pre-migration backup and monthly isolated restore check.
- [ ] Run focused operations tests.

### Task 8: Full verification and handoff

- [ ] Run all audit-focused tests and the complete suite.
- [ ] Run Ruff and the React build/typecheck.
- [ ] Record baseline unrelated failures separately from new failures.
- [ ] Inspect the diff for accidental changes to pre-existing user files.
- [ ] Update the audit with implemented status, remaining known limitations and verification commands.
- [ ] Commit the isolated branch with focused commits and provide the branch/worktree path.

## Current execution status

Implemented in this worktree: Tasks 1 (formats, official scoring, non-noted states),
the question-level rank contract, the visual/timeout safety path, the React reader
updates, item-link weighting, and catalogue visibility. The standalone rank
resolver is covered by `tests/test_rank_service.py`.

Still deliberately not marked complete: automatic UNESS rank-job orchestration and
admin queue, immutable initial/final result versions, full composition mode,
operational encrypted backups, and the five decision-oriented dashboards. These are
listed in `docs/AUDIT_QCM_ANNALES_2026-08-15_SUIVI.md` and must not be inferred from
the passing scoring tests.
