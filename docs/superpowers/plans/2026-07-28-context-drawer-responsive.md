# Responsive Context Drawer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make secondary cockpit panels render as right-side overlay drawers at 900–1200 px while preserving the existing desktop, mobile, classic, and backend behavior.

**Architecture:** Add one small shared CSS/DOM helper for drawer semantics and breakpoint classes. Integrate it into Today and course detail, then audit the existing secondary panels in Revisions and Colleges; screens without such a panel remain unchanged. Page callbacks remain the source of truth for selection and actions.

**Tech Stack:** Python 3, NiceGUI/Quasar, CSS media queries, pytest.

## Global Constraints

- Keep the classic path untouched.
- Do not modify backend or persistence behavior.
- Inject CSS synchronously during page build via `ui.add_head_html`.
- Use existing `--*` design tokens and transitions no longer than 180 ms.
- Drawer range is `min-width: 900px` and `max-width: 1199.98px`.
- At `>=1200px`, preserve the current desktop panel layout.
- At `<900px`, do not override the shell/mobile behavior reserved for session 3.

---

### Task 1: Shared responsive drawer contract

**Files:**
- Create: `frontend/components/responsive_drawer.py`
- Create: `tests/test_responsive_drawer.py`

**Interfaces:**
- Produces `responsive_drawer.ensure_styles()` for synchronous CSS injection.
- Produces `responsive_drawer.drawer_css_contract()` returning the stable class/attribute names used by pages.
- Produces `responsive_drawer.drawer_close_js()` only if the integration needs a shared browser-side Escape/scrim helper; otherwise keep the behavior in page-owned callbacks.

- [ ] **Step 1: Write the failing pure-contract tests**

```python
from frontend.components.responsive_drawer import drawer_css_contract


def test_drawer_contract_exposes_expected_classes_and_breakpoint():
    contract = drawer_css_contract()

    assert contract["root"] == "synapse-responsive-drawer"
    assert contract["scrim"] == "synapse-responsive-drawer__scrim"
    assert contract["panel"] == "synapse-responsive-drawer__panel"
    assert contract["close"] == "synapse-responsive-drawer__close"
    assert contract["breakpoint"] == "(min-width: 900px) and (max-width: 1199.98px)"
```

- [ ] **Step 2: Run the focused test and verify the expected missing-module failure**

Run: `pytest tests/test_responsive_drawer.py::test_drawer_contract_exposes_expected_classes_and_breakpoint -q`

Expected: FAIL because `frontend.components.responsive_drawer` does not exist yet.

- [ ] **Step 3: Implement the minimal contract and synchronous token-based styles**

Implement `drawer_css_contract()` with the exact values above and `ensure_styles()` with one idempotent `ui.add_head_html` block. The CSS must leave the root in normal flow by default, activate fixed right-side panel + scrim only in the 900–1199.98 px media query, hide drawer-only chrome outside that range, and use `var(--*)` tokens for color, spacing, shadow, and duration.

- [ ] **Step 4: Run the focused test and the component import smoke test**

Run: `pytest tests/test_responsive_drawer.py -q`

Expected: PASS with no import or collection errors.

- [ ] **Step 5: Commit the shared primitive**

```bash
git add frontend/components/responsive_drawer.py tests/test_responsive_drawer.py
git commit -m "feat: add shared responsive drawer contract"
```

### Task 2: Today context panel integration

**Files:**
- Modify: `frontend/pages/dashboard/_cockpit_today.py`
- Modify: `frontend/components/context_panel.py` only if a stable close button hook is needed
- Create or modify: `tests/test_cockpit_today_responsive.py`

**Interfaces:**
- Consumes the contract from `frontend.components.responsive_drawer`.
- Preserves `_on_select`, `_on_done`, `_on_postpone`, `_on_ignore`, `_open_focus`, and `context_panel(..., on_close=...)` behavior.
- Produces markup containing one drawer root, one scrim, one close control, and the existing context-panel content.

- [ ] **Step 1: Write the failing markup/behavior tests**

```python
from pathlib import Path


TODAY = Path("frontend/pages/dashboard/_cockpit_today.py").read_text(encoding="utf-8")


def test_today_uses_shared_responsive_drawer_contract():
    assert "responsive_drawer" in TODAY
    assert "synapse-responsive-drawer" in TODAY


def test_today_keeps_context_close_callback():
    assert "on_close=" in TODAY
```

- [ ] **Step 2: Run the focused tests and verify they fail for the missing integration**

Run: `pytest tests/test_cockpit_today_responsive.py -q`

Expected: FAIL because Today does not yet reference the shared drawer contract.

- [ ] **Step 3: Implement the Today integration**

Call `responsive_drawer.ensure_styles()` synchronously beside the existing component style calls. Wrap the current `ct-panel` in the shared drawer structure. Keep the desktop grid at `>=1200px`; at 900–1199.98 px move the panel to the fixed drawer layer and show the scrim. Make `✕` call the existing selection-close path without clearing the selected task, and add a compact reopen control only in drawer range if the current markup needs one.

- [ ] **Step 4: Run focused tests and existing Today-related tests**

Run: `pytest tests/test_cockpit_today_responsive.py tests/test_study_task_row_navigation.py tests/test_cockpit_shell.py -q`

Expected: PASS.

- [ ] **Step 5: Commit Today integration**

```bash
git add frontend/pages/dashboard/_cockpit_today.py frontend/components/context_panel.py tests/test_cockpit_today_responsive.py
git commit -m "feat: make today context panel a responsive drawer"
```

### Task 3: Course detail panel integration

**Files:**
- Modify: `frontend/pages/course_detail_cockpit.py`
- Create or modify: `tests/test_course_detail_responsive.py`

**Interfaces:**
- Consumes the shared drawer contract without changing course-detail data loading, tabs, OIC panel loading, or navigation links.
- Produces the existing `.ci-panel` content inside the responsive drawer layer.

- [ ] **Step 1: Write the failing integration tests**

```python
from pathlib import Path


DETAIL = Path("frontend/pages/course_detail_cockpit.py").read_text(encoding="utf-8")


def test_course_detail_uses_shared_responsive_drawer_contract():
    assert "responsive_drawer" in DETAIL
    assert "synapse-responsive-drawer" in DETAIL


def test_course_detail_keeps_context_panel_class():
    assert "ci-panel" in DETAIL
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `pytest tests/test_course_detail_responsive.py -q`

Expected: FAIL because the course-detail page does not yet use the shared primitive.

- [ ] **Step 3: Implement the course-detail integration**

Inject the shared styles synchronously during page build. Wrap the current `.ci-panel` in the drawer root/scrim structure, add the shared close affordance, and preserve all existing panel contents and callbacks. Do not change the `q-tabs`/`q-tab-panels` hierarchy or the OIC lazy-load behavior.

- [ ] **Step 4: Run focused and course-detail regression tests**

Run: `pytest tests/test_course_detail_responsive.py tests/test_course_detail_oic_tab.py tests/test_knowledge_course_detail_data.py -q`

Expected: PASS.

- [ ] **Step 5: Commit course-detail integration**

```bash
git add frontend/pages/course_detail_cockpit.py tests/test_course_detail_responsive.py
git commit -m "feat: make course detail panel a responsive drawer"
```

### Task 4: Audit Revisions and Colleges secondary panels

**Files:**
- Modify: `frontend/pages/todo_cockpit.py` only if the existing `.rv-panel` is secondary and can use the shared contract without changing its controls
- Modify: `frontend/pages/colleges_cockpit.py` only if the existing `.cg-panel` is secondary and can use the shared contract without changing its controls
- Create or modify: `tests/test_secondary_panels_responsive.py`

**Interfaces:**
- Consumes the same shared drawer contract.
- Does not invent a drawer for pages whose panel is a primary dashboard element or whose current interaction is not context-like.

- [ ] **Step 1: Write audit tests against the intended decision**

```python
from pathlib import Path


def test_revisions_panel_is_marked_for_responsive_treatment():
    source = Path("frontend/pages/todo_cockpit.py").read_text(encoding="utf-8")
    assert "rv-panel" in source


def test_colleges_panel_is_marked_for_responsive_treatment():
    source = Path("frontend/pages/colleges_cockpit.py").read_text(encoding="utf-8")
    assert "cg-panel" in source
```

- [ ] **Step 2: Run the audit tests**

Run: `pytest tests/test_secondary_panels_responsive.py -q`

Expected: PASS as an inventory test; use the result and the README screen criteria to decide whether each panel is secondary.

- [ ] **Step 3: Apply the shared drawer only to qualifying panels**

For each qualifying panel, add synchronous shared styles, wrap the panel in the shared drawer structure, and preserve its current controls. If a panel is not context-like, leave the page untouched and record that decision in the journal rather than forcing a drawer.

- [ ] **Step 4: Run page-specific regressions**

Run: `pytest tests/test_todo_cockpit_ui.py tests/test_weak_points_cockpit_ui.py tests/test_colleges_cockpit_ui.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the audit result**

```bash
git add frontend/pages/todo_cockpit.py frontend/pages/colleges_cockpit.py tests/test_secondary_panels_responsive.py
git commit -m "feat: adapt secondary cockpit panels responsively"
```

### Task 5: Full verification and handoff documentation

**Files:**
- Modify: `design_handoff_synapse_refonte/CLAUDE.md`
- Modify: `docs/superpowers/plans/2026-07-28-context-drawer-responsive.md`

- [ ] **Step 1: Run the complete relevant test set**

Run: `pytest tests/test_responsive_drawer.py tests/test_cockpit_today_responsive.py tests/test_course_detail_responsive.py tests/test_secondary_panels_responsive.py tests/test_cockpit_shell.py tests/test_focus_mode_cockpit.py -q`

Expected: PASS with no collection errors.

- [ ] **Step 2: Perform browser checks at the exact breakpoints**

Check 1200 px, 1000 px, 900 px, 899 px, and 768 px for Today and course detail. Confirm automatic drawer visibility in the target range, scrim layering, `✕`, `Escape`, outside click, selection persistence, reopen behavior, dark mode, and no classic-path regression.

- [ ] **Step 3: Update the journal and checklist**

Mark the session 2/3 portion of Étape 17 complete, record which pages received the shared drawer and which were intentionally unchanged, and preserve the pointer to session 3/3 mobile Aujourd’hui.

- [ ] **Step 4: Review the diff and commit documentation**

Run: `git diff --check; git status --short`

Then commit only the checklist/journal updates:

```bash
git add design_handoff_synapse_refonte/CLAUDE.md docs/superpowers/plans/2026-07-28-context-drawer-responsive.md
git commit -m "docs: record responsive drawer session"
```
