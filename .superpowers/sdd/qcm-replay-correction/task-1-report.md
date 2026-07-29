# Task 1 report

## Files changed

- `backend/core/reviews/local_store.py`
- `tests/test_ai_practice.py`

## Commit

- `a3df2f54de2559a4765904cfb75ecd0c27694070` — `feat: add QCM replay read models`

## Tests run

- `pytest tests/test_ai_practice.py -k "summary or history_filter" -v` — 2 passed, 16 deselected.
- `pytest tests/test_ai_practice.py -v` — 18 passed.

Both runs emitted one pre-existing `RequestsDependencyWarning` from the installed requests dependencies.

## Self-review

- Added dictionary-based session summary and bounded history read models.
- Latest attempts are selected by `MAX(id)` per session/question.
- History matching is case-insensitive across course title and item number, with pending/completed filters.
- Existing public signatures and immutable question/correction persistence were preserved.
- No explanation payloads are loaded by the history query.

## Concerns

- The existing dependency warning remains; it is unrelated to this task.

## Round 1 fix

- Validated the source session's stored question set before inserting a replay child.
- Empty question sets now raise `ValueError("Session IA sans questions rejouables : <id>")` and leave the database unchanged.
- Added `test_empty_ai_practice_session_cannot_be_replayed`.

## Round 1 verification

- `pytest tests/test_ai_practice.py -k "empty_ai_practice_session_cannot_be_replayed" -v` — 1 passed, 18 deselected.
- `pytest tests/test_ai_practice.py -v` — 19 passed.

Both runs emitted the same pre-existing `RequestsDependencyWarning`.
