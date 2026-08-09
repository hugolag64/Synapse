# Learning Metrics Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the ambiguous learning metric label `Progression` with explicit, consistently wired `Avancement`, `Maîtrise`, and `Rétention` metrics across the affected Synapse views.

**Architecture:** Add one pure frontend adapter that normalizes the three existing metric sources without changing database fields or algorithms. Migrate the Collèges and Semestres views first, then audit Items, the Item detail view, and Statistiques so learning metrics use the shared vocabulary while interaction-specific progress bars keep their local meaning.

**Tech Stack:** Python 3.11, NiceGUI, pytest, existing `mastery_score` / `mastery_level` / `retention_score` snapshots, Chromium QA on the homeserver.

## Global Constraints

- `Avancement` means read courses divided by expected courses.
- `Maîtrise` means the existing `mastery_score` and `mastery_level` evidence-backed score.
- `Rétention` means the existing projected `retention_score`, stability, and last evidence.
- Do not derive mastery or retention from reading progress.
- `None` must remain an explicit unknown state and must not render as `0 %`.
- A validated college counts all of its courses as read before avancement is calculated.
- Do not change mastery formulas, retention formulas, SQLite columns, or external evidence producers.
- Update `DEPLOYMENT_SESSION_2026-08-09.md` after each implementation tranche.
- Commit and push each completed tranche on `main` before homeserver deployment.

---

### Task 1: Add the shared learning-metrics adapter

**Files:**
- Create: `frontend/components/learning_metrics.py`
- Create: `tests/test_learning_metrics_contract.py`

**Interfaces:**
- Produces `build_advancement(done, total, *, college_validated=False) -> dict[str, int | None]` with keys `done`, `total`, and `percent`.
- Produces `build_learning_metrics(*, done, total, college_validated=False, mastery_score=None, mastery_level=None, retention_score=None, retention_stability_days=None, retention_last_evidence=None) -> dict` with top-level keys `advancement`, `mastery`, and `retention`.
- Later view tasks consume these dictionaries without reading alternate fields or reconstructing scores.

- [ ] **Step 1: Write failing contract tests**

```python
from datetime import date

from frontend.components.learning_metrics import build_advancement, build_learning_metrics


def test_advancement_is_read_over_total():
    assert build_advancement(12, 20) == {"done": 12, "total": 20, "percent": 60}


def test_validated_college_marks_all_courses_read():
    assert build_advancement(0, 20, college_validated=True) == {
        "done": 20,
        "total": 20,
        "percent": 100,
    }


def test_unknown_total_does_not_become_zero_percent():
    assert build_advancement(None, None) == {"done": None, "total": None, "percent": None}
    assert build_advancement(0, 0) == {"done": 0, "total": 0, "percent": None}


def test_mastery_and_retention_remain_independent():
    metrics = build_learning_metrics(
        done=20,
        total=20,
        mastery_score=None,
        mastery_level=None,
        retention_score=64,
        retention_stability_days=12.5,
        retention_last_evidence=date(2026, 8, 9),
    )
    assert metrics["mastery"] == {"score": None, "level": None}
    assert metrics["retention"] == {
        "score": 64,
        "stability_days": 12.5,
        "last_evidence": date(2026, 8, 9),
    }
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `pytest tests/test_learning_metrics_contract.py -q`

Expected: FAIL because `frontend.components.learning_metrics` does not exist yet.

- [ ] **Step 3: Implement the smallest pure adapter**

Implement `build_advancement` so that it:

1. Preserves `None` for unknown `done` or `total`.
2. Returns `percent=None` when `total` is `None` or `total <= 0`.
3. Replaces `done` with `total` when `college_validated=True` and `total` is known.
4. Computes `round(done / total * 100)` only when both counts are known and valid.

Implement `build_learning_metrics` as a thin composition of `build_advancement` plus the existing mastery and retention field names. It must not clamp, infer, or recalculate mastery or retention.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run: `pytest tests/test_learning_metrics_contract.py -q`

Expected: all contract tests PASS.

- [ ] **Step 5: Commit the adapter**

```bash
git add frontend/components/learning_metrics.py tests/test_learning_metrics_contract.py
git commit -m "feat: add shared learning metrics contract"
git push origin main
```

### Task 2: Migrate the Collèges cockpit

**Files:**
- Modify: `frontend/pages/colleges_cockpit.py` (`_course_semantics`, `_pilotage_summary`, `_draw_topbar`, `_draw_pilotage`, and the item-grid labels)
- Modify: `tests/test_colleges_cockpit_items.py`
- Modify: `tests/test_colleges_cockpit_ui.py`

**Interfaces:**
- Consumes `build_advancement` and `build_learning_metrics` from Task 1.
- Preserves the existing row keys (`reading_pct`, `lecture_label`, `mastery_score`, `retention_by_course`) so unrelated callers remain compatible.
- Produces visible labels `Avancement de lecture`, `Maîtrise moyenne`, and `Rétention` with distinct values.

- [ ] **Step 1: Add failing assertions for the shared vocabulary and unknown states**

Add tests that assert:

```python
source = open("frontend/pages/colleges_cockpit.py", encoding="utf-8").read()
assert "Avancement par matière" in source
assert "Avancement de lecture" in source
assert 'progression par matiÃ¨re' not in source
```

Add a row test with an unread course and no mastery evidence asserting `reading_pct == 0`, `mastery_score is None`, and no derived mastery score. Keep the validated-college test and make it assert that the adapter-backed row still reports `lecture_label == "Lu"` with `mastery_score is None`.

- [ ] **Step 2: Run the focused cockpit tests and verify the new assertions fail**

Run: `pytest tests/test_colleges_cockpit_items.py tests/test_colleges_cockpit_ui.py -q`

Expected: the new vocabulary assertion fails on the existing `progression par matière` subtitle.

- [ ] **Step 3: Wire the adapter without changing formulas**

Import the adapter. Replace the local `started / total` percentage calculation in `_pilotage_summary` with `build_advancement`, preserving the existing `pct` key for compatibility. Update `_course_semantics` to use the same adapter for the one-course read state and keep its existing status labels. Rename only the learning metric subtitle and explanatory copy; keep `Lecture`, `Maîtrise`, `Statut`, `Retard`, `Prochaine`, and `QCM` as separate columns.

For the pilotage cards, keep mastery and retention as separate entries and use `—` when their source values are absent. Do not use the avancement percentage as a fallback for either card.

- [ ] **Step 4: Run the focused cockpit tests and verify they pass**

Run: `pytest tests/test_colleges_cockpit_items.py tests/test_colleges_cockpit_ui.py tests/test_learning_metrics_contract.py -q`

Expected: all focused tests PASS.

- [ ] **Step 5: Commit the Collèges tranche**

```bash
git add frontend/pages/colleges_cockpit.py tests/test_colleges_cockpit_items.py tests/test_colleges_cockpit_ui.py
git commit -m "feat: clarify college advancement metric"
git push origin main
```

### Task 3: Migrate Semestres and preserve interaction progress semantics

**Files:**
- Modify: `frontend/pages/semestres_cockpit.py` (`render_semestres_cockpit`)
- Create: `tests/test_semestres_cockpit_ui.py`

**Interfaces:**
- Consumes `build_advancement` from Task 1.
- Keeps the existing semester hierarchy and course selection unchanged.
- Produces `Avancement par UE / semestre` and an empty-state-safe percentage.

- [ ] **Step 1: Write failing semester tests**

Add a pure helper in the page for the card metric, then test it with simple course-like objects:

```python
from types import SimpleNamespace

from frontend.pages.semestres_cockpit import _semester_advancement


def test_semester_advancement_counts_read_courses():
    courses = [SimpleNamespace(date_1ere_lecture="2026-08-01"), SimpleNamespace(date_1ere_lecture=None)]
    assert _semester_advancement(courses) == {"done": 1, "total": 2, "percent": 50}


def test_semester_advancement_has_no_false_zero_for_empty_input():
    assert _semester_advancement([]) == {"done": 0, "total": 0, "percent": None}
```

Add a source assertion that the subtitle is `Avancement par UE / semestre`.

- [ ] **Step 2: Run the focused semester tests and verify they fail**

Run: `pytest tests/test_semestres_cockpit_ui.py -q`

Expected: FAIL because `_semester_advancement` and the new subtitle do not exist.

- [ ] **Step 3: Implement the helper and rename only the learning metric**

Implement `_semester_advancement(courses)` by counting `date_1ere_lecture`, passing the counts to `build_advancement`, and using `metric["percent"]` for the card label and bar width. When the percentage is `None`, render `—` and zero-width neutral styling instead of a misleading `0 %` learning score. Leave weekly-goal bars and interaction-specific progress labels unchanged.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_semestres_cockpit_ui.py tests/test_learning_metrics_contract.py -q`

Expected: all focused tests PASS.

- [ ] **Step 5: Commit the Semestres tranche**

```bash
git add frontend/pages/semestres_cockpit.py tests/test_semestres_cockpit_ui.py
git commit -m "feat: label semester advancement explicitly"
git push origin main
```

### Task 4: Align Statistiques navigation and protect Item semantics

**Files:**
- Modify: `frontend/pages/stats.py` (`stats_page`)
- Modify: `frontend/pages/dashboard/_dialogs.py` (weekly-bilan navigation action)
- Modify: `frontend/cockpit_shell.py` (`_TITLE_TO_NAV` compatibility aliases)
- Create: `tests/test_learning_metrics_surfaces.py`

**Interfaces:**
- Consumes the shared metric vocabulary from Task 1.
- Does not rename progress bars that measure QCM questions, import jobs, weekly goals, OIC completion, or another interaction-local quantity.

- [ ] **Step 1: Add failing regression checks for navigation and scope boundaries**

Add tests that assert:

```python
stats_source = open("frontend/pages/stats.py", encoding="utf-8").read()
dashboard_source = open("frontend/pages/dashboard/_dialogs.py", encoding="utf-8").read()
shell_source = open("frontend/cockpit_shell.py", encoding="utf-8").read()

assert 'with frame("Statistiques")' in stats_source
assert "Voir mes statistiques" in dashboard_source
assert '"Statistiques": "Statistiques"' in shell_source
```

Also assert that `frontend/pages/items.py` and `frontend/pages/course_detail_cockpit.py` do not introduce a generic learning-metric label `Progression`. Keep `Progression des objectifs` in `stats.py` explicitly allowed because it measures weekly goals, not course learning coverage.

- [ ] **Step 2: Run the focused surface tests and verify they fail**

Run: `pytest tests/test_learning_metrics_surfaces.py -q`

Expected: FAIL because the statistics page and dashboard action still use `Ma Progression` / `Voir ma progression`.

- [ ] **Step 3: Rename the statistics navigation without changing interaction progress**

Change the stats page frame to `frame("Statistiques")`, change the dashboard action to `Voir mes statistiques`, and keep `_TITLE_TO_NAV["Statistiques"] = "Statistiques"` as the canonical mapping. Retain aliases for `Ma Progression` and `Stats` so older callers do not break. Do not change OIC objective progress, QCM session progress, weekly objectives, or import progress labels because those are not the learning contract defined in the spec.

- [ ] **Step 4: Run the focused surface tests**

Run: `pytest tests/test_learning_metrics_surfaces.py tests/test_items_sorting.py tests/test_course_detail_oic_tab.py tests/test_learning_metrics_contract.py -q`

Expected: all focused tests PASS.

- [ ] **Step 5: Commit the audit tranche**

```bash
git add frontend/pages/stats.py frontend/pages/dashboard/_dialogs.py frontend/cockpit_shell.py tests/test_learning_metrics_surfaces.py
git commit -m "fix: clarify statistics navigation label"
git push origin main
```

### Task 5: Full verification, Chromium QA, and deployment journal

**Files:**
- Modify: `DEPLOYMENT_SESSION_2026-08-09.md`

**Interfaces:**
- Consumes all completed metric-contract tranches.
- Produces a reproducible homeserver deployment handoff and QA record.

- [ ] **Step 1: Run the complete automated test suite**

Run: `pytest -q`

Expected: all tests PASS; record warnings separately without treating them as metric failures.

- [ ] **Step 2: Deploy the current `main` on the homeserver**

```bash
cd /srv/docker/stacks/synapse
git pull --ff-only origin main
docker compose build --pull synapse
docker compose up -d --force-recreate synapse
```

- [ ] **Step 3: QA the four routes in Chromium**

Check `/colleges`, `/items`, `/stats`, and one `/cours/<id>` route. Record the visible labels, a known-data state, an unknown-data state, and browser `error`/`warning` logs. Confirm that `Avancement`, `Maîtrise`, and `Rétention` are not aligned to the wrong values.

- [ ] **Step 4: Update the deployment journal**

Record the commit hashes, test result, deployed asset/version when applicable, routes checked, and any remaining issues in `DEPLOYMENT_SESSION_2026-08-09.md`.

- [ ] **Step 5: Commit and push the journal**

```bash
git add DEPLOYMENT_SESSION_2026-08-09.md
git commit -m "docs: record learning metrics QA"
git push origin main
```

## Self-review checklist

- The plan covers all contract, UI, missing-data, test, and QA requirements from the design spec.
- No database migration or algorithm recalibration is included.
- `mastery_score` and `retention_score` remain independent throughout every task.
- Interaction-local progress labels are explicitly protected from accidental renaming.
- Every implementation task has a focused test cycle and a commit boundary.
