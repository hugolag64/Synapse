# QCM Node Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the NiceGUI QCM reader/correction dialogs with a Node/React QCM experience matching the approved Synapse mockups.

**Architecture:** Keep Synapse’s Python/NiceGUI cockpit and SQLite domain services. Add a small FastAPI JSON boundary for QCM session reads, answer persistence, completion and replay. Add a Vite/React frontend for the QCM reader and correction page; development runs on its own port and production serves the built assets from the Python app.

**Tech Stack:** Python/FastAPI/SQLite, Node.js, React, Vite, TypeScript, CSS tokens from `static/synapse.css`.

## Global Constraints

- Existing AI practice questions remain immutable.
- Scores and attempt persistence remain computed by Python services, never by the browser.
- Existing NiceGUI QCM analytics and manual score entry remain available during migration.
- The Node frontend must support pending sessions, completed correction, error-only filtering and exact replay.
- No external network call is required for local QCM navigation.

---

### Task 1: Add the API contract and failing backend tests

**Files:**
- Create: `backend/api/qcm.py`
- Modify: `main.py`
- Test: `tests/test_qcm_api.py`

**Interfaces:**
- `GET /api/qcm/sessions/{session_id}` returns session metadata, questions and latest responses.
- `POST /api/qcm/sessions/{session_id}/attempts` accepts `{question_id, response}`.
- `POST /api/qcm/sessions/{session_id}/complete` finalizes and returns the correction summary.
- `POST /api/qcm/sessions/{session_id}/replay` returns the new session id.

- [ ] Write tests for session payload, attempt persistence, completion and replay.
- [ ] Run `pytest tests/test_qcm_api.py -q` and confirm failure because the API module/routes do not exist.
- [ ] Implement typed request/response adapters over `local_store` and `qcm_replay` helpers.
- [ ] Register the router in `main.py` without changing the NiceGUI page routes.
- [ ] Run the focused tests and the existing replay tests.
- [ ] Commit: `feat: expose QCM practice API`.

### Task 2: Scaffold the Node QCM application

**Files:**
- Create: `qcm_app/package.json`
- Create: `qcm_app/tsconfig.json`
- Create: `qcm_app/vite.config.ts`
- Create: `qcm_app/index.html`
- Create: `qcm_app/src/main.tsx`
- Create: `qcm_app/src/styles.css`

**Interfaces:**
- Development command: `npm --prefix qcm_app run dev`.
- Production command: `npm --prefix qcm_app run build`.
- Browser entry: `/qcm-app/?session=<id>`.

- [ ] Add the minimal React/Vite dependencies and scripts.
- [ ] Add a smoke test or build check that proves the bundle compiles.
- [ ] Run `npm --prefix qcm_app run build` and confirm the empty shell builds.
- [ ] Commit: `feat: scaffold Node QCM frontend`.

### Task 3: Implement the approved session reader

**Files:**
- Create: `qcm_app/src/api.ts`
- Create: `qcm_app/src/types.ts`
- Create: `qcm_app/src/SessionReader.tsx`
- Modify: `qcm_app/src/main.tsx`
- Modify: `qcm_app/src/styles.css`

**Interfaces:**
- `fetchSession(sessionId: number): Promise<QcmSession>`.
- `saveAttempt(sessionId: number, questionId: number, response: string): Promise<void>`.
- Reader states: loading, question, saving, error, completed.

- [ ] Add component tests for question count, checkbox answers, previous/next navigation and restored answers.
- [ ] Run the tests and confirm they fail before the reader exists.
- [ ] Implement the reader with the approved spacious layout, progress header, question body, answer controls and anchored bottom actions.
- [ ] Persist an answer before moving forward and preserve unanswered state on back navigation.
- [ ] Run component tests and the production build.
- [ ] Commit: `feat: add Node QCM session reader`.

### Task 4: Implement the approved correction screen

**Files:**
- Create: `qcm_app/src/CorrectionView.tsx`
- Modify: `qcm_app/src/api.ts`
- Modify: `qcm_app/src/main.tsx`
- Modify: `qcm_app/src/styles.css`

**Interfaces:**
- `completeSession(sessionId: number): Promise<QcmCorrection>`.
- `replaySession(sessionId: number): Promise<number>`.

- [ ] Add component tests for KPI values, correct/incorrect cards, error-only filtering and replay action.
- [ ] Run the tests and confirm failure before the correction view exists.
- [ ] Implement the full-page visual from the approved mockup: `Synapse / QCM` header, date/title, KPI strip, expandable answer cards, “Pourquoi ?” explanation panel, filter and footer actions.
- [ ] Keep correction content readable on long sessions and narrow screens.
- [ ] Run component tests and build.
- [ ] Commit: `feat: add Node QCM correction view`.

### Task 5: Connect NiceGUI entry points to Node

**Files:**
- Modify: `frontend/pages/qcm_cockpit.py`
- Modify: `frontend/components/ai_practice_panel.py`
- Modify: `main.py`
- Create: `qcm_app/README.md`
- Test: `tests/test_qcm_node_entry.py`

**Interfaces:**
- NiceGUI launches `/qcm-app/?session=<id>` for pending sessions and completed corrections.
- `main.py` serves the built `qcm_app/dist` assets when present and provides a clear fallback when the bundle is absent.

- [ ] Add failing source/UI tests for the Node entry URL and the no-bundle fallback.
- [ ] Implement the route handoff while preserving history, delete-pending and manual QCM actions.
- [ ] Add build instructions and local development proxy configuration.
- [ ] Run Python tests, Node tests and the production build.
- [ ] Commit: `feat: route Synapse QCM flows to Node frontend`.

### Task 6: Verify and publish

**Files:**
- Modify: `docs/PROGRESSION_SESSION_2026-07-29.md`

- [ ] Run `pytest -q`.
- [ ] Run `npm --prefix qcm_app run build`.
- [ ] Manually verify `/qcm-app/?session=<id>` for pending, completed, correction filter and replay.
- [ ] Inspect `git diff --check` and verify no unrelated files are included.
- [ ] Update the progress note with the final architecture and commands.
- [ ] Commit: `docs: document Node QCM frontend integration`.
