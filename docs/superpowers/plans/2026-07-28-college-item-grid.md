# College Item Grid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make expanded college rows use the available width and expose item-level learning signals.

**Architecture:** Keep the existing college-level aggregation and render a shared compact grid inside each expanded college. Extend the item-row preparation helper with per-course mastery, urgency, next review, and QCM values so rendering remains presentation-only.

**Tech Stack:** Python, NiceGUI, existing review service and CSS token system, pytest.

## Global Constraints

- Limit changes to the Colleges cockpit and focused tests.
- Reuse existing review/task/QCM calculations; do not add per-item backend queries.
- Preserve title navigation and the existing validation dialog.
- Use existing semantic CSS tokens for status colors.

### Task 1: Prepare item-level status data

**Files:**
- Modify: `frontend/pages/colleges_cockpit.py` (`_college_item_rows` and its caller)
- Test: `tests/test_colleges_cockpit_ui.py`

**Interfaces:**
- Consumes the existing course list, generated tasks, mastery map, and QCM map.
- Produces item dictionaries containing `course`, `task`, `pct`, `level`, `urgent`, `next_task`, and `qcm_score`.

- [ ] Add a focused test for the helper: an item with a task and score exposes its level, urgency, next task, and score; an item without data exposes `None` values.
- [ ] Run `pytest tests/test_colleges_cockpit_ui.py -q` and confirm the new test fails before implementation.
- [ ] Update `_college_item_rows` to accept the already-computed maps and derive item-level values without new service calls.
- [ ] Run the focused test and confirm it passes.
- [ ] Commit with `feat: expose item signals in college details`.

### Task 2: Render the expanded item grid

**Files:**
- Modify: `frontend/pages/colleges_cockpit.py` (`_CSS`, `_draw_row`)
- Test: `tests/test_colleges_cockpit_ui.py`

**Interfaces:**
- Consumes the item dictionaries from Task 1.
- Produces a header plus aligned item cells for progression, status, retard, fragile, next review, QCM, and the existing validation action.

- [ ] Add source-level assertions for the seven column labels, readable non-started styling, and removal of the old “aucune révision prévue” rendering path.
- [ ] Run the focused test and confirm it fails against the old markup.
- [ ] Add responsive grid/flex styles and render the item-level values with semantic colors; use `—` only for absent values.
- [ ] Preserve click propagation boundaries for title, validation, and status navigation.
- [ ] Run the focused test and confirm it passes.
- [ ] Run `python -m compileall frontend/pages/colleges_cockpit.py`.
- [ ] Commit with `feat: add college item status grid`.
