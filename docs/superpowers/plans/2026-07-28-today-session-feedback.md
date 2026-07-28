# Aujourd’hui cockpit — Retour de séance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route the Today cockpit `Terminer` action through the shared session-feedback wizard and existing mastery pipeline.

**Architecture:** Keep `open_session_feedback_dialog`, `complete_review`, and `record_evaluation` unchanged. Add one Today-page callback that opens the shared wizard, then let its existing `_on_done` callback persist the full evaluation and rebuild the page.

**Tech Stack:** Python, NiceGUI, pytest, existing SQLite evaluation facade.

## Global Constraints

- No change to the mastery algorithm, lacune thresholds, backend, classic path, or wizard fields.
- `Terminer` must open `open_session_feedback_dialog` before validation.
- The wizard callback must preserve named fields through `complete_review`.

---

### Task 1: Reconnect Today cockpit validation

**Files:**
- Modify: `frontend/pages/dashboard/_cockpit_today.py`
- Create: `tests/test_cockpit_today_session_feedback.py`

**Interfaces:**
- Consumes: `open_session_feedback_dialog(task, card, validate_fn)` from `frontend.pages.dashboard._dialogs`.
- Produces: Today source markup/callback wiring where `context_panel` opens the wizard and passes `_on_done` as `validate_fn`.

- [ ] **Step 1: Write the failing characterization tests**

```python
from pathlib import Path


SOURCE = Path("frontend/pages/dashboard/_cockpit_today.py").read_text(encoding="utf-8")


def test_today_termine_opens_shared_session_feedback_wizard():
    assert "open_session_feedback_dialog" in SOURCE
    assert "validate_fn=_on_done" in SOURCE


def test_today_keeps_full_feedback_fields_on_done_callback():
    assert "qcm_result=qcm_result" in SOURCE
    assert "weak_category=weak_category" in SOURCE
    assert "weak_detail=weak_detail" in SOURCE
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `pytest tests/test_cockpit_today_session_feedback.py -q`

Expected: FAIL because Today currently calls `_on_done` directly and never references the shared wizard.

- [ ] **Step 3: Implement the smallest UI wiring change**

Import `open_session_feedback_dialog` in `_cockpit_today.py`. Add a local `_open_feedback(task)` function that creates a hidden UI card/element and calls:

```python
open_session_feedback_dialog(task, card, _on_done)
```

Change the context-panel `on_done` callback from:

```python
on_done=lambda t: asyncio.create_task(_on_done(t))
```

to:

```python
on_done=_open_feedback
```

Leave `_on_done` unchanged so it continues to call `complete_review` with every feedback field.

- [ ] **Step 4: Run the focused and persistence tests**

Run: `pytest tests/test_cockpit_today_session_feedback.py tests/test_review_completion_service.py tests/test_evaluation_service.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the functional fix**

```bash
git add frontend/pages/dashboard/_cockpit_today.py tests/test_cockpit_today_session_feedback.py
git commit -m "fix: reconnect today session feedback wizard"
```

### Task 2: Verify the complete regression surface

**Files:**
- Modify: `design_handoff_synapse_refonte/CLAUDE.md`

- [ ] **Step 1: Run the full test suite**

Run: `pytest -q`

Expected: all tests pass; only the two known external/deprecation warnings may remain.

- [ ] **Step 2: Update the journal**

Record that Aujourd’hui cockpit now opens the shared wizard and feeds `complete_review → record_evaluation(source="auto_eval")`; note that the wizard and mastery algorithm were intentionally unchanged.

- [ ] **Step 3: Commit the journal update**

```bash
git add design_handoff_synapse_refonte/CLAUDE.md
git commit -m "docs: record today feedback reconnection"
```
