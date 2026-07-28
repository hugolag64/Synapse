# Weak Points Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make cockpit weak-point cards interactive and fill the unused right side with a useful pilotage panel.

**Architecture:** Reuse the existing `WeakPointCard` component and its local-store callbacks instead of duplicating action logic. Expand the cockpit content to a full-width two-column layout and derive a pure summary from the rows already loaded.

**Tech Stack:** Python, NiceGUI, existing local weak-point store, pytest.

## Global Constraints

- Preserve the classic Kanban view unchanged.
- Reuse existing weak-point actions and storage methods.
- Keep the Obsidian sync action in the cockpit header.
- Use `Créer une lacune` as the visible creation action.

### Task 1: Add the weak-point summary helper

**Files:**
- Modify: `frontend/pages/weak_points_cockpit.py`
- Test: `tests/test_weak_points_cockpit_ui.py`

**Interfaces:** `_weak_point_summary(rows)` returns counts by status, severity and source type.

- [ ] Add a failing test with active, critical, recurrent, resolved and source-tagged rows.
- [ ] Run the focused test to verify it fails before the helper exists.
- [ ] Implement the pure summary helper.
- [ ] Run the focused test and verify it passes.

### Task 2: Reuse interactive cards and fill the layout

**Files:**
- Modify: `frontend/pages/weak_points_cockpit.py`
- Test: `tests/test_weak_points_cockpit_ui.py`

**Interfaces:** `_draw_card` delegates to `WeakPointCard(w, on_refresh=_render)`; `_draw_pilotage` renders the summary in the right column.

- [ ] Add source assertions for `WeakPointCard`, `Créer une lacune`, full-width content, and the pilotage panel.
- [ ] Run the focused test to verify it fails against the current bespoke card.
- [ ] Remove the content max-width, add a two-column content body, replace the bespoke card with `WeakPointCard`, and render the summary panel.
- [ ] Run focused tests and compile the module.
- [ ] Run the full test suite and commit the implementation.
