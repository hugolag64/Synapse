# PDF Path Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose a visible PDF replacement action wherever a stale local PDF path can be encountered.

**Architecture:** Reuse `open_pdf_wizard` and its existing persistence path. Add only UI entry points and source-level regression tests; do not duplicate file search or persistence logic.

**Tech Stack:** Python, NiceGUI, pytest.

## Global Constraints

- Keep `open_pdf_wizard` as the only PDF repair flow.
- Do not change backend path resolution or PDF search scoring.
- Preserve classic and cockpit behavior apart from the new repair action.

---

### Task 1: Expose PDF replacement actions

**Files:**
- Modify: `frontend/pages/course_detail_cockpit.py`
- Modify: `frontend/components/context_panel.py`
- Modify: `frontend/components/course_card.py`
- Create: `tests/test_pdf_path_repair_ui.py`

- [ ] **Step 1: Write the failing source tests**

```python
from pathlib import Path


def test_course_detail_always_exposes_pdf_repair():
    source = Path("frontend/pages/course_detail_cockpit.py").read_text(encoding="utf-8")
    assert "Modifier le PDF" in source


def test_today_context_panel_exposes_pdf_repair():
    source = Path("frontend/components/context_panel.py").read_text(encoding="utf-8")
    assert "Modifier le PDF" in source


def test_classic_course_card_exposes_pdf_repair_for_existing_pdf():
    source = Path("frontend/components/course_card.py").read_text(encoding="utf-8")
    assert "Modifier le PDF" in source
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `pytest tests/test_pdf_path_repair_ui.py -q`

Expected: FAIL because the existing surfaces only expose opening/searching, not replacement.

- [ ] **Step 3: Add the three UI actions**

Reuse `open_pdf_wizard(course, context, refresh_fn, client)` with the current course object. In the context panel resolve the course by `task.course_id` from `data_store.cours` and use `ui.navigate.reload` as the refresh callback. Keep the existing open-PDF action unchanged.

- [ ] **Step 4: Run focused and existing PDF tests**

Run: `pytest tests/test_pdf_path_repair_ui.py tests/test_files.py tests/test_store_pdf.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the UI repair action**

```bash
git add frontend/pages/course_detail_cockpit.py frontend/components/context_panel.py frontend/components/course_card.py tests/test_pdf_path_repair_ui.py
git commit -m "feat: expose pdf path repair actions"
```

### Task 2: Verify and document

**Files:**
- Modify: `design_handoff_synapse_refonte/CLAUDE.md`

- [ ] **Step 1: Run the full suite**

Run: `pytest -q`

Expected: all tests pass with only the known warnings.

- [ ] **Step 2: Record the repair workflow**

Document that stale PDF paths can be replaced from the three surfaces and that the Settings auto-link remains the bulk repair path.

- [ ] **Step 3: Commit documentation**

```bash
git add design_handoff_synapse_refonte/CLAUDE.md
git commit -m "docs: record pdf path repair workflow"
```
