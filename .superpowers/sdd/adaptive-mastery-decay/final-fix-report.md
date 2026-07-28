# Adaptive mastery decay — final fix report

## Files

- `backend/core/knowledge/retention.py`: enforce the shared 25-point floor for current, aged, and no-evidence retention scores.
- `backend/core/reviews/mastery.py`: tolerate a missing Anki evidence capability; add deduplicated canonical QCM/DP/KFP and OIC attempt evidence; seed dated lecture evidence when no study-session row exists; remove the unreachable `à entraîner` action branch.
- `frontend/components/forgetting_curve.py`: apply the shared floor to the legacy projection fallback.
- `tests/test_knowledge_retention.py`, `tests/test_knowledge_mastery.py`, `tests/test_forgetting_curve.py`: regressions for every reviewed behavior, including canonical-evidence de-duplication.

## Tests and output

- Focused: `pytest -q tests/test_knowledge_retention.py tests/test_knowledge_mastery.py tests/test_forgetting_curve.py` — `32 passed, 1 warning`.
- Full relevant suite: `pytest -q` — `549 passed, 2 warnings`.

## Concerns

- The two full-suite warnings are pre-existing third-party/event-loop warnings from `requests` and `test_delete_course_action`.
- `git diff --check` still reports only pre-existing trailing whitespace in unrelated `frontend/pages/qcm.py:78-79`; this fix wave does not modify that file.
