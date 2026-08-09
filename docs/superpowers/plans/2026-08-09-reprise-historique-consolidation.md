# Reprise historique consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route the ten validated legacy colleges directly into consolidation with a local start gate of 2026-08-20, while preserving Notion data and existing SQLite evidence.

**Architecture:** Add a local per-course consolidation gate, add a batch helper that identifies courses belonging to validated colleges and having an item state, and make normal J-cycle generation skip those courses. A standalone idempotent migration script will dry-run or apply the college status, missing item states, gates, and first consolidation anchors.

**Tech Stack:** Python 3.11, SQLite, pytest, Pydantic course cache, existing SM-2 consolidation service, Docker Compose runtime.

## Global Constraints

- Do not modify Notion dates or properties.
- Preserve existing `item_state` levels and review evidence.
- Missing legacy item states default to `correct`, never `solide`.
- No synthetic J3/J7/J14/J30 history rows.
- No targeted consolidation task is visible before 2026-08-20.
- The migration must be idempotent and create a SQLite backup before `--apply`.

---

### Task 1: Persist per-course consolidation start gates

**Files:**
- Modify: `backend/core/reviews/local_store.py` in `init_db()` and the consolidation API section.
- Test: `tests/test_consolidation.py`.

**Interfaces:**
- Produce `set_consolidation_not_before(course_id: str, context: str, not_before: datetime.date, source: str = "reprise_historique") -> None`.
- Produce `get_consolidation_not_before(course_id: str, context: str) -> datetime.date | None`.
- Produce `get_consolidation_not_before_map(context: str = "college") -> dict[str, datetime.date]`.

- [ ] **Step 1: Write failing gate tests**

Add tests for an absent gate, an upserted gate, and a batch map containing only the requested context.

- [ ] **Step 2: Run the focused tests and verify failure**

Run `pytest tests/test_consolidation.py -k not_before -q`; expect missing-function failures.

- [ ] **Step 3: Add the SQLite table and API**

Create `consolidation_gates(course_id, context, not_before, source, created_at, updated_at)` with a composite primary key. Use the existing `_conn()` and `_now()` helpers and `ON CONFLICT(course_id, context) DO UPDATE`.

- [ ] **Step 4: Run focused tests**

Run `pytest tests/test_consolidation.py -k not_before -q`; expect all gate tests to pass.

- [ ] **Step 5: Commit**

Commit as `feat: add consolidation start gates`.

### Task 2: Identify historically completed courses and route them

**Files:**
- Modify: `backend/core/knowledge/service.py` with `get_historically_completed_course_ids(courses, context="college")`.
- Modify: `backend/core/reviews/service.py` in `generate_reviews()`.
- Modify: `backend/core/reviews/consolidation.py` in `get_due_consolidation_tasks()`.
- Test: `tests/test_knowledge_service.py` and `tests/test_consolidation.py`.

**Interfaces:**
- `get_historically_completed_course_ids(courses: list, context: str = "college") -> set[str]` returns course IDs whose college list intersects a `college_status.status == "valide"` college and whose `(course_id, context)` has an `item_state`.

- [ ] **Step 1: Write failing tests**

Test that a course with a validated college and item state is returned, while a course without the state or with an unvalidated college is not. Test that normal J tasks omit a historical course and consolidation accepts it even when its Notion J dates are incomplete.

- [ ] **Step 2: Run focused tests and verify failure**

Run `pytest tests/test_knowledge_service.py tests/test_consolidation.py -k historical -q`; expect failures because the helper and routing do not exist.

- [ ] **Step 3: Implement the batch helper**

Load `get_all_college_statuses()` and `get_all_item_states(context)` once, derive the validated college set, and return IDs without per-course SQL queries.

- [ ] **Step 4: Skip normal J generation for historical IDs**

In `ReviewService.generate_reviews()`, compute the set once before iterating courses and `continue` for historical college courses before reading `date_1ere_lecture`.

- [ ] **Step 5: Allow historical IDs in consolidation**

In `get_due_consolidation_tasks()`, compute the same set once and bypass the `is_j_cycle_complete()` requirement only for those IDs. Apply the gate map: skip when `today < not_before`, otherwise use `max(due, not_before)` as the effective due date.

- [ ] **Step 6: Run focused tests**

Run `pytest tests/test_knowledge_service.py tests/test_consolidation.py -k historical -q` and then the full consolidation and knowledge test files.

- [ ] **Step 7: Commit**

Commit as `feat: route historical courses to consolidation`.

### Task 3: Create the idempotent historical reprise command

**Files:**
- Create: `deploy/reprise_historique_consolidation.py`.
- Test: `tests/test_reprise_historique_consolidation.py`.
- Modify: `deploy/README-UBUNTU.md` with dry-run/apply commands.

**Interfaces:**
- CLI requires exactly one of `--dry-run` or `--apply`.
- Constants include the ten exact college names and `START_DATE = date(2026, 8, 20)`.
- `build_report(courses, states, college_statuses) -> dict` returns counts by college and missing-state IDs.

- [ ] **Step 1: Write failing report tests**

Test the ten-college target set, 176-course report shape with representative fixtures, default `correct` missing states, and idempotent missing-state selection.

- [ ] **Step 2: Run focused tests and verify failure**

Run `pytest tests/test_reprise_historique_consolidation.py -q`; expect import/function failures.

- [ ] **Step 3: Implement dry-run**

Load the cache using `data_store.load_from_disk(force=True)`, compute target courses by college intersection, report existing/missing states, and report the number of gates and status changes without writing SQLite.

- [ ] **Step 4: Implement apply**

Call `local_store.backup_database()` first. Add only missing validated-college status, create only missing `item_state` rows with `correct` and `source="reprise_historique"`, set gates for all target course IDs, and bootstrap only courses without an existing consolidation state with an anchor equal to `START_DATE - initial_interval_days` so their first due date is 2026-08-20.

- [ ] **Step 5: Run focused tests**

Run `pytest tests/test_reprise_historique_consolidation.py -q` and verify that a second apply plan reports zero missing states and zero new status changes.

- [ ] **Step 6: Commit**

Commit as `feat: add historical consolidation reprise command`.

### Task 4: Validate the package and server dry-run

**Files:**
- Verify: `docker-compose.yml`, `deploy/reprise_historique_consolidation.py`, and the modified services.

- [ ] **Step 1: Run complete local validation**

Run `pytest -q`, `python -m compileall -q backend frontend deploy`, and `docker compose config --quiet`.

- [ ] **Step 2: Publish the branch**

Push `codex/ubuntu-clean-deploy` and provide the server pull/rebuild commands.

- [ ] **Step 3: Run server dry-run only**

Run inside the container:

```bash
docker compose exec -T synapse python deploy/reprise_historique_consolidation.py --dry-run
```

Require the report to show ten target colleges, 176 targeted courses, and 30 missing item states before applying.

- [ ] **Step 4: Apply only after report verification**

Run `docker compose exec -T synapse python deploy/reprise_historique_consolidation.py --apply`, then verify the SQLite backup path, counts, and no pre-2026-08-20 consolidation tasks.
