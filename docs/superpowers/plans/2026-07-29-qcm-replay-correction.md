# QCM Replay and Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox ( - [ ] ) syntax for tracking.

**Goal:** Add a usable history, replay flow, and end-of-session correction view for generated/imported QCM sessions while preserving immutable questions and existing analytics.

**Architecture:** Keep persistence in backend/core/reviews/local_store.py, add pure session/correction helpers in a focused frontend component module, and integrate the existing QCM cockpit with a selected-session workspace. Reuse the existing AI practice attempt, finalization, and replay APIs; only add the read/update helpers required for resume and correction.

**Tech Stack:** Python 3, NiceGUI, SQLite, pytest, existing Synapse CSS variables and cockpit components.

## Global Constraints

- Only generated/imported sessions with stored questions are replayable.
- Questions and their corrections remain immutable.
- A replay creates a new session linked to its source session.
- Manual score-only QCM entries remain analytical and are not made replayable.
- Missing explanations, unanswered questions, interrupted sessions, and persistence failures must render as recoverable UI states.
- Existing QCM statistics and AI practice tests must remain green.

---

### Task 1: Add read-model helpers for replay and correction

**Files:**
- Modify: backend/core/reviews/local_store.py near get_ai_practice_session, record_ai_practice_attempt, and finalize_ai_practice_session
- Test: tests/test_ai_practice.py

**Interfaces:**
- Produces get_ai_practice_session_summary(session_id: int) -> dict | None with session metadata, answered_count, scored_count, correct_count, incorrect_count, unanswered_count, and the latest attempt per question.
- Produces get_ai_practice_sessions_history(limit: int = 100, query: str = "", status: str = "all") -> list[dict] for the cockpit history list, including session metadata and counts without loading every explanation.
- Existing get_ai_practice_session, record_ai_practice_attempt, finalize_ai_practice_session, and replay_ai_practice_session signatures remain compatible.

- [ ] Step 1: Write failing persistence tests

Create a three-question session, record one correct and one incorrect answer, then assert the summary reports one unanswered question and uses only the latest attempt per question. Add a history test for query matching on course_title/item_number and status filtering for pending/completed sessions.

- [ ] Step 2: Run focused tests and verify failure

Run: pytest tests/test_ai_practice.py -k "summary or history_filter" -v
Expected: FAIL because the new helper functions do not exist.

- [ ] Step 3: Implement the minimal SQL read models

Use the existing connection wrapper and the same MAX(id) per (session_id, question_id) pattern as finalize_ai_practice_session. Keep the history query bounded by LIMIT, perform case-insensitive matching consistently, and return plain dictionaries so NiceGUI does not depend on sqlite row objects.

- [ ] Step 4: Run focused and existing practice tests

Run: pytest tests/test_ai_practice.py -k "summary or history_filter" -v
Then run: pytest tests/test_ai_practice.py -v
Expected: PASS.

- [ ] Step 5: Commit

git add backend/core/reviews/local_store.py tests/test_ai_practice.py
git commit -m "feat: add QCM replay read models"

### Task 2: Extract pure answer/correction view models

**Files:**
- Create: frontend/components/qcm_replay.py
- Modify: frontend/components/ai_practice_panel.py
- Test: tests/test_qcm_replay.py

**Interfaces:**
- Create build_question_result(question: dict, latest_attempt: dict | None) -> dict returning status, response, correct_answer, explanation, choices, and is_open.
- Create build_session_result(questions: list[dict]) -> dict returning counts and score_percent based on the latest attempt for each question.
- Create filter_question_results(results: list[dict], errors_only: bool) -> list[dict].
- Keep _same_closed_answer(response: str, answer: str, choices: list[str]) -> bool as the canonical closed-question comparison function, imported by the new module rather than duplicated.

- [ ] Step 1: Write failing pure-function tests

Cover correct, incorrect, unanswered, open-question-without-automatic-status, missing explanation, multiple-choice answers in a different order, score calculation, and errors-only filtering.

- [ ] Step 2: Run tests and verify failure

Run: pytest tests/test_qcm_replay.py -v
Expected: FAIL because frontend/components/qcm_replay.py is absent.

- [ ] Step 3: Implement the view-model functions

Normalize attempt data by selecting the latest attempt already supplied by the store. Closed questions use _same_closed_answer only when the persisted attempt has no explicit is_correct; open questions preserve None status and display the expected answer without claiming automatic correctness. Use "Explication non disponible" when the stored explanation is blank.

- [ ] Step 4: Move shared answer comparison ownership without changing behavior

Import the canonical comparator from qcm_replay.py in ai_practice_panel.py or place it in the new module and re-export it. Preserve existing behavior for multi-answer closed questions.

- [ ] Step 5: Run focused and existing tests

Run: pytest tests/test_qcm_replay.py tests/test_ai_practice.py -v
Expected: PASS.

- [ ] Step 6: Commit

git add frontend/components/qcm_replay.py frontend/components/ai_practice_panel.py tests/test_qcm_replay.py
git commit -m "feat: model QCM correction results"

### Task 3: Build the resumable session reader

**Files:**
- Modify: frontend/components/ai_practice_panel.py around _open_answer_dialog
- Modify: frontend/components/qcm_replay.py
- Test: tests/test_qcm_replay.py

**Interfaces:**
- Produce open_qcm_session(session_id: int, on_complete: Callable[[int], None], on_back: Callable[[], None]) -> None.
- The reader restores the latest response for the current session, renders closed choices and open text inputs, supports previous/next navigation, and exposes a final Corriger mes réponses action.

- [ ] Step 1: Add a testable response-state helper

Add latest_response_by_question(questions: list[dict]) -> dict[int, str] and tests proving interrupted sessions restore the newest response for each question while leaving unanswered questions blank.

- [ ] Step 2: Run the focused test and verify failure

Run: pytest tests/test_qcm_replay.py -k latest_response -v
Expected: FAIL because the helper is not defined.

- [ ] Step 3: Implement the response-state helper and reader UI

Replace the current all-questions modal submission flow with a step-based reader. Keep answers in local UI state while navigating, save each question through local_store.record_ai_practice_attempt when advancing or finishing, call local_store.finalize_ai_practice_session(session_id), then call record_ai_practice_mastery(session_id) only after all questions have been answered/scored as the current flow expects. Keep a close/back action that does not finalize an incomplete session.

- [ ] Step 4: Add failure notifications and empty-session handling

If get_ai_practice_session returns no questions, notify the user and do not open the dialog. If saving/finalizing fails, leave the dialog open, preserve local answers, and show a retry notification.

- [ ] Step 5: Run relevant tests

Run: pytest tests/test_qcm_replay.py tests/test_ai_practice.py tests/test_evaluation_reconnection.py -v
Expected: PASS.

- [ ] Step 6: Commit

git add frontend/components/ai_practice_panel.py frontend/components/qcm_replay.py tests/test_qcm_replay.py
git commit -m "feat: add resumable QCM reader"

### Task 4: Build the correction view

**Files:**
- Modify: frontend/components/qcm_replay.py
- Modify: frontend/components/ai_practice_panel.py
- Test: tests/test_qcm_replay.py

**Interfaces:**
- Produce open_qcm_correction(session_id: int, on_back: Callable[[], None], on_replay: Callable[[int], None]) -> None.
- The view consumes get_ai_practice_session_summary and get_ai_practice_session, then renders the summary, question rows, expandable detail, errors-only filter, return action, and replay action.

- [ ] Step 1: Add pure rendering-data tests

Assert that a finished two-out-of-three session renders the expected score/counts, that unanswered questions get an explicit status, that a blank explanation gets the fallback label, and that errors-only removes correct questions but keeps incorrect and unanswered questions.

- [ ] Step 2: Run tests and verify failure

Run: pytest tests/test_qcm_replay.py -k correction -v
Expected: FAIL until the correction data contract is implemented.

- [ ] Step 3: Implement the correction UI

Use the approved layout: score summary at the top, compact question list, status color/icon, expandable question body, selected response, correct response, and explanation. Keep the default compact so long sessions do not become a wall of text. Add the errors-only toggle and make the current question expansion local to the dialog/page.

- [ ] Step 4: Wire replay and navigation actions

The replay button calls local_store.replay_ai_practice_session(session_id), not the original session mutation path, then opens the new session reader. Return closes the correction and restores the history/selected-session view.

- [ ] Step 5: Run focused tests

Run: pytest tests/test_qcm_replay.py tests/test_ai_practice.py -v
Expected: PASS.

- [ ] Step 6: Commit

git add frontend/components/qcm_replay.py frontend/components/ai_practice_panel.py tests/test_qcm_replay.py
git commit -m "feat: add QCM correction view"

### Task 5: Integrate the history and selected-session workspace into the QCM cockpit

**Files:**
- Modify: frontend/pages/qcm_cockpit.py
- Modify: frontend/components/qcm_replay.py
- Test: tests/test_qcm_cockpit_replay.py

**Interfaces:**
- Add cockpit-local selected session state and _render_history(...) and _render_selected_session(...) functions.
- Existing KPI summary, course rollup, pending sessions, and Nouvelle session menu remain available.

- [ ] Step 1: Add source-level/UI contract tests

Assert the cockpit imports the replay reader/correction actions, exposes a search field/filter, shows a replayable-session history section, and retains the existing pending-session Commencer action and QCM entry menu.

- [ ] Step 2: Run tests and verify failure

Run: pytest tests/test_qcm_cockpit_replay.py -v
Expected: FAIL because the history workspace is not wired into the cockpit.

- [ ] Step 3: Implement the two-column workspace

Keep the current analytical summary at the top. Add a bounded history column with search/filter and a main selected-session area. Sessions with stored questions show Reprendre, Voir la correction, and Rejouer; score-only analytical rows are not mixed into this replay list. Use existing design tokens and responsive CSS so the history stacks above the main area on narrow screens.

- [ ] Step 4: Preserve pending-session behavior

Route pending AI sessions to the new reader while keeping the existing SESSIONS À FAIRE section and refresh callback. After completion or replay, refresh the KPI/course rollup and the selected history entry.

- [ ] Step 5: Run cockpit and regression tests

Run: pytest tests/test_qcm_cockpit_replay.py tests/test_cockpit_shell.py tests/test_frontend_shell_import.py tests/test_ai_practice.py -v
Expected: PASS.

- [ ] Step 6: Commit

git add frontend/pages/qcm_cockpit.py frontend/components/qcm_replay.py tests/test_qcm_cockpit_replay.py
git commit -m "feat: integrate QCM replay history into cockpit"

### Task 6: Verify long-session UX and full regression safety

**Files:**
- Modify: tests/test_qcm_replay.py only if an uncovered regression is found
- Modify: tests/test_qcm_cockpit_replay.py only if an uncovered regression is found

- [ ] Step 1: Run the complete targeted suite

Run: pytest tests/test_ai_practice.py tests/test_qcm_replay.py tests/test_qcm_cockpit_replay.py tests/test_evaluation_reconnection.py tests/test_cockpit_shell.py tests/test_frontend_shell_import.py -v

- [ ] Step 2: Run the full test suite

Run: pytest -q
Expected: no new failures.

- [ ] Step 3: Manually verify the rendered flows

Start Synapse, open QCM, generate/import a session with at least 10 questions, answer all questions, inspect the correction summary, expand an incorrect question, toggle errors-only, return to history, and replay the source session. Also verify an interrupted session restores answers and that the history remains usable with at least 20 sessions.

- [ ] Step 4: Commit any test-only adjustments

git add tests/test_qcm_replay.py tests/test_qcm_cockpit_replay.py
git commit -m "test: cover QCM replay regression paths"
