# First Reading Action Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give an item with no first-reading date a clear primary action in the cockpit detail.

**Architecture:** Reuse the existing tracking dialog and existing task detection. Only the primary CTA branch changes in `course_detail_cockpit.py`; no algorithm or backend changes.

**Tech Stack:** Python, NiceGUI, pytest.

## Global Constraints

- Keep `open_start_tracking_dialog` as the source of truth for first-reading and J3/J7/J14/J30 dates.
- Keep `Modifier les dates` as a secondary action.
- Preserve classic behavior.

---

### Task 1: Add the missing primary action

**Files:**
- Modify: `frontend/pages/course_detail_cockpit.py`
- Create: `tests/test_course_detail_first_reading_action.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path


SOURCE = Path("frontend/pages/course_detail_cockpit.py").read_text(encoding="utf-8")


def test_detail_offers_start_study_when_first_reading_is_missing():
    assert "Commencer l'étude" in SOURCE
    assert "open_start_tracking_dialog" in SOURCE


def test_detail_keeps_due_review_action():
    assert "Réviser maintenant" in SOURCE
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `pytest tests/test_course_detail_first_reading_action.py -q`

Expected: FAIL because the current disabled CTA has no first-reading branch.

- [ ] **Step 3: Implement the state-based CTA**

Compute `has_first_read = bool(course.date_1ere_lecture)` for the college context. Render `Commencer l'étude` and call `open_start_tracking_dialog(course, "college", lambda: ui.navigate.reload(), ui.context.client, is_restart=False)` when `task is None` and `has_first_read` is false. When the first reading exists but no task is due, render `Ouvrir le cours` linking to the PDF/detail resource. Preserve the existing Focus action when `task` is present.

- [ ] **Step 4: Run focused and detail regression tests**

Run: `pytest tests/test_course_detail_first_reading_action.py tests/test_course_detail_oic_tab.py tests/test_knowledge_course_detail_data.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/course_detail_cockpit.py tests/test_course_detail_first_reading_action.py
git commit -m "feat: expose first reading action in cockpit detail"
```

### Task 2: Verify and document

**Files:**
- Modify: `design_handoff_synapse_refonte/CLAUDE.md`

- [ ] **Step 1: Run the full suite**

Run: `pytest -q`

Expected: all tests pass with only known warnings.

- [ ] **Step 2: Record the CTA state machine in the journal**

Document the three states: start study, open course, revise now.

- [ ] **Step 3: Commit documentation**

```bash
git add design_handoff_synapse_refonte/CLAUDE.md
git commit -m "docs: record first reading action"
```
