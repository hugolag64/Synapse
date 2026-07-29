# Final fix report — QCM replay/correction

## Files changed

- `frontend/components/qcm_replay.py`: added stable-slot dialog chaining, state-derived actions, blank-response handling, and JSON closed-choice serialization/restoration with legacy parsing.
- `frontend/pages/qcm_cockpit.py`: opens completion/replay dialogs under the captured page slot, gates actions by persisted state, uses aggregate replayability, and displays score/duration metadata.
- `frontend/components/ai_practice_panel.py`: uses stable slots for generated/replayed dialog chains, gates pending/completed actions, and displays stored score/duration metadata.
- `backend/core/reviews/local_store.py`: ignores blank legacy attempts in readers/summaries/finalization, adds aggregate `has_questions` and latest-duration history fields, exposes completion state to detailed history, and applies scoped Ruff modernization.
- `tests/test_qcm_replay.py`: adds behavior coverage for stable dialog transitions, blank attempts, JSON comma-safe persistence/restoration, and backward-compatible response parsing.
- `tests/test_qcm_cockpit_replay.py`: adds behavior coverage for state-gated actions, a single bounded aggregate history query, replayability exclusion, score, and duration.
- `tests/test_qcm_cockpit_ui.py`: covers completed scoreless sessions being excluded from pending actions.
- `tests/test_ai_practice.py`: imports the closed-answer behavior from its owning replay module after the unused UI import was removed.
- `.superpowers/sdd/qcm-replay-correction/task-4-report.md`: corrects the feature commit to the branch-local commit.
- `.superpowers/sdd/qcm-replay-correction/final-fix-report.md`: this report.

## Commit

This report is included in the single commit `fix: harden QCM replay transitions and persistence`; its final hash is returned with the task result.

## Tests and output

- Red phase: `pytest tests/test_qcm_replay.py tests/test_qcm_cockpit_replay.py -v` produced the expected 8 regression failures before implementation.
- Focused suite: `pytest tests/test_ai_practice.py tests/test_qcm_replay.py tests/test_qcm_cockpit_replay.py tests/test_qcm_cockpit_ui.py tests/test_evaluation_reconnection.py tests/test_cockpit_shell.py tests/test_frontend_shell_import.py -v` — 66 passed, 1 existing `RequestsDependencyWarning`, in 3.32s.
- Full suite: `pytest -q` — 725 passed, 2 warnings, in 14.32s on the final tree.
- Ruff: `ruff check frontend/pages/qcm_cockpit.py frontend/components/qcm_replay.py frontend/components/ai_practice_panel.py backend/core/reviews/local_store.py tests/test_qcm_replay.py tests/test_qcm_cockpit_replay.py tests/test_qcm_cockpit_ui.py` — all checks passed.
- Diff hygiene: `git diff --check` — passed.

## Self-review

- Completion-to-correction and replay-to-reader transitions refresh first, then create the next dialog under a stable page slot instead of the deleted source slot.
- Pending sessions expose only resume/start; completed sessions expose correction/replay and cannot be edited in place. Completed scoreless sessions are not misclassified as pending.
- Empty responses are not saved by the reader. Existing blank attempts are ignored by restoration, summaries, history aggregates, and finalization, so they remain explicitly unanswered.
- Cockpit history obtains replayability, latest answer counts, score, and duration from one bounded aggregate query; it no longer hydrates every candidate session or loops through its questions.
- Closed selections are stored as JSON labels, restored losslessly when a label contains a comma, and legacy comma-separated values remain readable.
- Question/correction immutability, replay eligibility, manual analytical rows, deferred partial finalization, and retry idempotence remain covered by the focused and full suites.

## Remaining concerns

- The environment still emits the pre-existing `requests` dependency-version warning and one unrelated asyncio deprecation warning in the full suite.
- The lifecycle regression uses the brief-approved stable-slot helper test; no separate browser-driven NiceGUI completion/replay run was added.
