# Task 4 report — QCM correction view

## Files changed

- `frontend/components/qcm_replay.py`: added correction summary/row view models and the immutable correction dialog, including errors-only filtering and replay handling.
- `frontend/components/ai_practice_panel.py`: opens correction after step-reader completion and from completed history entries; replayed sessions return to the step reader.
- `tests/test_qcm_replay.py`: added the completed two-out-of-three correction-summary and row test. Existing tests cover explicit unanswered status, explanation fallback, and errors-only filtering.
- `.superpowers/sdd/qcm-replay-correction/task-4-report.md`: this report.

## Commit

`3a181d93816bdb3fa73710cad2ae08d899399bb0` — `feat: add QCM correction view`

## Tests run/output

`pytest tests/test_qcm_replay.py tests/test_ai_practice.py -v`

Result: 31 passed, 1 existing `requests` dependency-version warning, in 2.26s.

## Self-review

- Correction reads both the stored session summary and its immutable questions.
- The compact list exposes status icon/colour, expand-on-demand prompt, selected response, correct response, and explanation fallback.
- Errors-only keeps incorrect, unanswered, and unscored rows.
- Return restores the caller's history view; replay creates a local replay session and opens the step reader.
- Empty/manual score-only sessions show the existing no-questions warning and cannot be replayed through this view.

## Concerns

- No concerns. The test command emits one pre-existing third-party `requests` dependency-version warning.
