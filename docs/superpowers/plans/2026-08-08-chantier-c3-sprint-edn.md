# Chantier C3 — Rendre visible ce que le Sprint EDN pilote Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Sprint EDN panel show what its current phase actually recommends (focus message
and the new/review/QCM-DP ratio breakdown), instead of just the phase name — then delete the dead
Streamlit widget that was the only other reader of those fields.

**Architecture:** Task 1 extends `edn_insights_model()` with 5 keys read straight off the already-
computed `SprintConfig`, and adds two `.edn-sprint-subtitle` lines to `render_edn_insights_panel()`.
Task 2 deletes `sprint_countdown_widget.py` now that nothing reads its fields anymore.

**Tech Stack:** NiceGUI (`ui.label`), pytest (`SimpleNamespace` fixtures for the model test, source-
text assertions for the render/dead-code guard tests — matches the existing style for these files).

## Global Constraints

- No change to `backend/core/planning/sprint_countdown.py` — `SprintCountdownService`,
  `SprintConfig`, the 120j/30j thresholds, and the per-phase ratio/message values are all reused
  exactly as computed today.
- The two new lines reuse the existing `.edn-sprint-subtitle` CSS class (`edn_insights_panel.py:84`)
  — no new CSS rule.
- `edn_target_date` configuration (Settings) is untouched.
- Full suite (`./.venv/Scripts/python.exe -m pytest -q`) run before Task 1 Step 1 and after the last
  step, zero regressions.

---

### Task 1: Surface focus message and ratio breakdown in the live panel

**Files:**
- Modify: `frontend/components/edn_insights_panel.py:11-25` (model) and `:100-123` (render)
- Modify: `tests/test_edn_insights_ui.py:1-25` (existing test's fixture + assertions)

**Interfaces:**
- Consumes: `status` (a `SprintConfig` or equivalent, already has `.recommended_new_ratio`,
  `.recommended_review_ratio`, `.recommended_qcm_dp_ratio`, `.daily_target_items`,
  `.focus_message` — all pre-existing fields on the dataclass, no change needed there).
- Produces: `edn_insights_model(status)` returns 5 additional keys:
  `"focus_message"` (str, passed through unchanged), `"new_ratio"` / `"review_ratio"` /
  `"qcm_dp_ratio"` (str, integer percent, e.g. `"25"`), `"daily_target_items"` (str). Task 2 does not
  depend on any of this.

- [ ] **Step 1: Run the full suite to record the baseline**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, 1152 tests (the count left by C2).

- [ ] **Step 2: Update the existing test's fixture and add new assertions**

In `tests/test_edn_insights_ui.py`, replace:

```python
def test_edn_insights_model_contains_progress_and_sprint_fields():
    from frontend.components.edn_insights_panel import edn_insights_model

    model = edn_insights_model(
        SimpleNamespace(
            days_remaining=73,
            target_date=SimpleNamespace(strftime=lambda _fmt: "15/10/2026"),
            phase=SimpleNamespace(value="consolidation"),
            covered_items=20,
            total_items=367,
            average_mastery=61.5,
            overdue_reviews=4,
            remaining_reviews=28,
        )
    )

    assert model["countdown"] == "J-73"
    assert model["coverage"] == "20/367"
    assert model["mastery"] == "61.5 %"
    assert model["overdue"] == "4"
```

with:

```python
def test_edn_insights_model_contains_progress_and_sprint_fields():
    from frontend.components.edn_insights_panel import edn_insights_model

    model = edn_insights_model(
        SimpleNamespace(
            days_remaining=73,
            target_date=SimpleNamespace(strftime=lambda _fmt: "15/10/2026"),
            phase=SimpleNamespace(value="consolidation"),
            covered_items=20,
            total_items=367,
            average_mastery=61.5,
            overdue_reviews=4,
            remaining_reviews=28,
            recommended_new_ratio=0.25,
            recommended_review_ratio=0.45,
            recommended_qcm_dp_ratio=0.30,
            daily_target_items=6,
            focus_message="🎯 Mode Consolidation : Entraînement QCM/DP quotidien et rattrapage des lacunes Rang A.",
        )
    )

    assert model["countdown"] == "J-73"
    assert model["coverage"] == "20/367"
    assert model["mastery"] == "61.5 %"
    assert model["overdue"] == "4"
    assert model["focus_message"] == "🎯 Mode Consolidation : Entraînement QCM/DP quotidien et rattrapage des lacunes Rang A."
    assert model["new_ratio"] == "25"
    assert model["review_ratio"] == "45"
    assert model["qcm_dp_ratio"] == "30"
    assert model["daily_target_items"] == "6"


def test_edn_insights_panel_renders_focus_message_and_ratio_breakdown():
    source = Path("frontend/components/edn_insights_panel.py").read_text(encoding="utf-8")
    start = source.index("def render_edn_insights_panel(")
    body = source[start:]

    assert 'model["focus_message"]' in body
    assert "model['new_ratio']" in body
    assert "model['review_ratio']" in body
    assert "model['qcm_dp_ratio']" in body
    assert "model['daily_target_items']" in body
```

Note: `focus_message` is checked with double quotes because it's used as a standalone expression
(`ui.label(model["focus_message"])`, not inside an f-string), while the other four are checked with
single quotes because they sit inside an f-string in the implementation
(`f"...{model['new_ratio']}..."`) — this file's established convention (see the existing
`model['countdown']` / `model['target']` usages) is single quotes for dict keys inside f-strings, to
avoid escaping the string's own double quotes.

`render_edn_insights_panel` is the last function in the file, so no end-marker is needed for this
scoped slice — `source[start:]` already stops at end-of-file.

- [ ] **Step 3: Run the tests to verify they fail for the right reason**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_edn_insights_ui.py -v`

Expected:
- `test_edn_insights_model_contains_progress_and_sprint_fields` — FAIL: `KeyError: 'focus_message'`
  (the model doesn't return this key yet).
- `test_edn_insights_panel_renders_focus_message_and_ratio_breakdown` — FAIL:
  `'model["focus_message"]' in body` is `False` (the render function doesn't reference it yet).
- `test_dashboard_reads_the_persisted_edn_target_date` — PASS (untouched).

- [ ] **Step 4: Extend the model and the render function**

In `frontend/components/edn_insights_panel.py`, replace:

```python
def edn_insights_model(status) -> dict[str, str]:
    mastery = "—" if status.average_mastery is None else f"{status.average_mastery:g} %"
    total_items = int(status.total_items or 0)
    covered_items = int(status.covered_items or 0)
    coverage_percent = min(100, covered_items / total_items * 100 if total_items else 0)
    return {
        "countdown": f"J-{status.days_remaining}",
        "target": status.target_date.strftime("%d/%m/%Y"),
        "phase": str(status.phase.value).replace("_", " ").title(),
        "coverage": f"{status.covered_items}/{status.total_items}",
        "coverage_percent": f"{coverage_percent:.1f}",
        "mastery": mastery,
        "overdue": str(status.overdue_reviews),
        "remaining": str(status.remaining_reviews),
    }
```

with:

```python
def edn_insights_model(status) -> dict[str, str]:
    mastery = "—" if status.average_mastery is None else f"{status.average_mastery:g} %"
    total_items = int(status.total_items or 0)
    covered_items = int(status.covered_items or 0)
    coverage_percent = min(100, covered_items / total_items * 100 if total_items else 0)
    return {
        "countdown": f"J-{status.days_remaining}",
        "target": status.target_date.strftime("%d/%m/%Y"),
        "phase": str(status.phase.value).replace("_", " ").title(),
        "coverage": f"{status.covered_items}/{status.total_items}",
        "coverage_percent": f"{coverage_percent:.1f}",
        "mastery": mastery,
        "overdue": str(status.overdue_reviews),
        "remaining": str(status.remaining_reviews),
        "focus_message": status.focus_message,
        "new_ratio": f"{int(status.recommended_new_ratio * 100)}",
        "review_ratio": f"{int(status.recommended_review_ratio * 100)}",
        "qcm_dp_ratio": f"{int(status.recommended_qcm_dp_ratio * 100)}",
        "daily_target_items": str(status.daily_target_items),
    }
```

Then, still in the same file, replace:

```python
    with ui.element("div").classes("edn-sprint-panel w-full p-4 mb-4"):
        with ui.element("div").classes("edn-sprint-header"):
            with ui.column().classes("gap-0"):
                ui.label(f"Sprint EDN · {model['countdown']}").classes("edn-sprint-title")
                ui.label(
                    f"Objectif {model['target']} · phase {model['phase']}"
                ).classes("edn-sprint-subtitle")
            with ui.element("div").classes("edn-sprint-stats"):
                for label, value in (
                    ("Items", model["coverage"]),
                    ("Maîtrise", model["mastery"]),
                    ("Retard", model["overdue"]),
                    ("Restant", model["remaining"]),
                ):
                    with ui.element("div").classes("edn-sprint-metric"):
                        ui.label(label).classes("edn-sprint-metric-label")
                        ui.label(value).classes("edn-sprint-metric-value")
        with ui.element("div").classes("edn-sprint-progress-track mt-3"):
            ui.element("div").classes("edn-sprint-progress-fill").style(
                f"width:{model['coverage_percent']}%"
            )
        if projections:
```

with:

```python
    with ui.element("div").classes("edn-sprint-panel w-full p-4 mb-4"):
        with ui.element("div").classes("edn-sprint-header"):
            with ui.column().classes("gap-0"):
                ui.label(f"Sprint EDN · {model['countdown']}").classes("edn-sprint-title")
                ui.label(
                    f"Objectif {model['target']} · phase {model['phase']}"
                ).classes("edn-sprint-subtitle")
                ui.label(model["focus_message"]).classes("edn-sprint-subtitle")
            with ui.element("div").classes("edn-sprint-stats"):
                for label, value in (
                    ("Items", model["coverage"]),
                    ("Maîtrise", model["mastery"]),
                    ("Retard", model["overdue"]),
                    ("Restant", model["remaining"]),
                ):
                    with ui.element("div").classes("edn-sprint-metric"):
                        ui.label(label).classes("edn-sprint-metric-label")
                        ui.label(value).classes("edn-sprint-metric-value")
        with ui.element("div").classes("edn-sprint-progress-track mt-3"):
            ui.element("div").classes("edn-sprint-progress-fill").style(
                f"width:{model['coverage_percent']}%"
            )
        ui.label(
            f"Répartition recommandée : {model['new_ratio']}% nouveaux · "
            f"{model['review_ratio']}% révisions · {model['qcm_dp_ratio']}% QCM/DP · "
            f"{model['daily_target_items']} items/j visés"
        ).classes("edn-sprint-subtitle mt-2")
        if projections:
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_edn_insights_ui.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/edn_insights_panel.py tests/test_edn_insights_ui.py
git commit -m "feat: surface Sprint EDN focus message and recommended ratio breakdown in the live panel"
```

---

### Task 2: Delete the dead Streamlit widget

**Files:**
- Delete: `frontend/components/sprint_countdown_widget.py`
- Test: `tests/test_edn_insights_ui.py` (extended with a dead-code guard)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: nothing consumed by a later task — this is the last task in the plan.

- [ ] **Step 1: Write the failing dead-code guard test**

Append to `tests/test_edn_insights_ui.py`:

```python
def test_streamlit_sprint_widget_is_gone():
    import subprocess

    widget_path = Path("frontend/components/sprint_countdown_widget.py")
    assert not widget_path.exists()

    result = subprocess.run(
        ["git", "grep", "-l", "render_sprint_countdown_widget", "--", "frontend", "backend"],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "", f"still referenced in: {result.stdout}"
```

The pathspec restricts the search to `frontend`/`backend` (live code) — without it, `git grep` also
matches this test file itself (the string is a literal argument right above) and
`docs/AUDIT_2026-08-03.md:132`, a frozen historical audit entry that already documented this exact
widget as having zero callers. Neither is a live reference worth failing on.

- [ ] **Step 2: Run the test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_edn_insights_ui.py::test_streamlit_sprint_widget_is_gone -v`
Expected: FAIL — `assert not widget_path.exists()` is `False` (the file is still there).

- [ ] **Step 3: Delete the file**

```bash
rm frontend/components/sprint_countdown_widget.py
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_edn_insights_ui.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, 1155 tests (1152 baseline + 3 net new: 2 from Task 1, 1 dead-code guard from Task
2), zero regressions.

- [ ] **Step 6: Update the tracking doc**

In `docs/UI_REFONTE_ETAT_DES_LIEUX.md`, mark C3 as terminé (commit hashes, tests before → after) in
the same table format used for A/B1-B4/C1/C2, and update the "▶ REPRISE" header to point at the next
open sub-chantier (C4, C5, or D). This file stays uncommitted, per the established convention for
this series of chantiers.

- [ ] **Step 7: Commit**

```bash
git add frontend/components/sprint_countdown_widget.py tests/test_edn_insights_ui.py
git commit -m "refactor: delete the dead Streamlit Sprint EDN widget, superseded by the live NiceGUI panel"
```

---

## Self-Review Notes

- **Spec coverage:** §1 (model extension) → Task 1 Step 4 (first replacement). §2 (render extension)
  → Task 1 Step 4 (second replacement). §3 (dead widget deletion) → Task 2 Step 3. Risks section
  (fixture `AttributeError`) → Task 1 Step 2 (fixture extended before the model is touched, so the
  test fails with `KeyError` on the *new* keys rather than crashing on missing attributes — since
  the fixture is updated in the same step as the assertions, not left stale).
- **Placeholder scan:** none found — every step has literal code, exact commands, exact expected
  output.
- **Type/name consistency:** `edn_insights_model()`'s five new keys (`focus_message`, `new_ratio`,
  `review_ratio`, `qcm_dp_ratio`, `daily_target_items`) are used with identical spelling in the model
  (Task 1 Step 4), the render function (Task 1 Step 4), and both tests that reference them (Task 1
  Step 2).
- **`git grep` availability check:** Task 2 Step 1 shells out to `git grep` rather than a Python-only
  search, to catch a reference in *any* tracked file (docs, scripts, not just `.py` test/source
  files already covered by the plan's own greps during design). This repo is a git repository
  (confirmed by every prior chantier in this series using `git commit`/`git push`), so `git grep` is
  always available here.
