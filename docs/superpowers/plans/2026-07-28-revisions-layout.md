# Revisions Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the Revisions queue, fill the unused page width with actionable summary information, and replace the static sidebar badge with the real overdue count.

**Architecture:** Convert the existing revision rows from flex sizing to a shared CSS grid. Add a lightweight right-side summary panel using the already-loaded task list. Make the cockpit sidebar compute the overdue count through the review service at render time.

**Tech Stack:** Python, NiceGUI, CSS grid, existing review service, pytest.

## Global Constraints

- Preserve the existing revision actions and focus mode callbacks.
- Reuse the current generated task list; do not add Notion or per-task queries.
- Keep the classic UI path unchanged.
- Show the sidebar count only when it is meaningful; use `0` when there are no overdue reviews.

### Task 1: Align the revision list

**Files:**
- Modify: `frontend/pages/todo_cockpit.py`
- Test: `tests/test_todo_cockpit_ui.py`

**Interfaces:** The existing `_draw_head` and `_draw_row` render the same six-column grid template.

- [ ] Add source assertions for the shared grid template and full-width list wrapper.
- [ ] Run the focused test and confirm it fails against the current flex CSS.
- [ ] Replace the flex header/row sizing with CSS grid columns shared by both selectors.
- [ ] Run the focused test and confirm it passes.

### Task 2: Add the revision pilotage panel

**Files:**
- Modify: `frontend/pages/todo_cockpit.py`
- Test: `tests/test_todo_cockpit_ui.py`

**Interfaces:** `_load_and_render` supplies `data["tasks"]` and `data["overdue"]`; `_draw_pilotage` renders derived counts.

- [ ] Add a pure summary helper covering overdue, today, upcoming, cycle counts, and estimated minutes.
- [ ] Test the helper with representative task objects.
- [ ] Add a two-column wrapper with the queue on the left and summary panel on the right.
- [ ] Render the summary panel without changing task callbacks.
- [ ] Run focused tests and compile the module.

### Task 3: Make the sidebar badge dynamic

**Files:**
- Modify: `frontend/cockpit_shell.py`
- Test: `tests/test_cockpit_shell.py`

**Interfaces:** `_revision_badge()` returns `("count", str(overdue_count))` for the existing `_nav_item` badge contract.

- [ ] Add a test that mocks the review service and verifies the badge equals the overdue task count.
- [ ] Replace the literal `("count", "2")` with `_revision_badge()` when building navigation.
- [ ] Run focused tests and the full test suite.
