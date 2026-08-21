# Chantier C2 — Marquer un item déjà vu avant Synapse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the already-existing "Niveau déclaré" (Solide/Correct/Flou) control into the item
cockpit's Vue d'ensemble tab, then delete the ~450 lines of dead code in `course_detail.py` that
hid it (unreachable since `course_detail_page()` returns unconditionally to the cockpit).

**Architecture:** Task 1 adds a new private function `_render_declared_level(course, mastery)` to
`course_detail_cockpit.py`, wired into `_tab_overview`, reusing the existing
`backend/core/knowledge/store.py` API unchanged. Task 2 deletes the dead code from
`course_detail.py` now that nothing in the live app depends on it, and corrects a test docstring
that references the removed function.

**Tech Stack:** NiceGUI (`ui.column`/`ui.button`/`ui.badge`), pytest (source-text assertions, no
module import — matches the existing test style for these page files).

## Global Constraints

- No change to `backend/core/knowledge/{models,service,store}.py` — the existing `get_item_state` /
  `set_item_state` API is reused exactly as-is.
- No OIC coverage line is ported — the cockpit's dedicated OIC tab (`render_oic_panel`) already
  covers that, and `mastery.oic_coverage_a` / `mastery.has_rang_a_badge` would be redundant with it.
- `positive` / `warning` / `negative` Quasar colors on the three level buttons are kept as-is — this
  is a genuine self-assessment signal (same category as "Difficulté" / "Résultat QCM" in the B2
  design-token rules), not a decorative color to convert.
- `_tab_overview(course, task, score, level, next_due, next_cycle, mastery, sessions)` signature is
  unchanged — `course` and `mastery` are already parameters.
- The `/triage/{college}` bulk page is untouched — out of scope for C2 (user decision).
- Full suite (`./.venv/Scripts/python.exe -m pytest -q`) run before Task 1 Step 1 and after the last
  step, zero regressions.

---

### Task 1: Add the declared-level control to the cockpit

**Files:**
- Modify: `frontend/pages/course_detail_cockpit.py:594-596` (insert new function + wire into
  `_tab_overview`)
- Test: `tests/test_declared_level_cockpit.py` (new)

**Interfaces:**
- Consumes: `course` (`.id`), `mastery` (unused by the new function itself — kept as a parameter for
  signature symmetry with the other `_tab_*` render helpers and because the caller already has it;
  the function only needs `course.id`), `knowledge_store.get_item_state(course_id, context)`,
  `knowledge_store.set_item_state(course_id, level, context, source)` (both already defined in
  `backend/core/knowledge/store.py`, unchanged), `review_service.invalidate_cache()` (already
  imported at the top of `course_detail_cockpit.py`, line 31).
- Produces: `_render_declared_level(course, mastery) -> None`, called once from `_tab_overview`. No
  other task depends on this — Task 2 only deletes code, it doesn't consume this function.

- [ ] **Step 1: Run the full suite to record the baseline**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, 1149 tests (the count left by C1). Task 2 Step 5 compares the final count against
this baseline plus the tests added in this plan.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_declared_level_cockpit.py`:

```python
from pathlib import Path

COCKPIT_SOURCE = (
    Path(__file__).parents[1] / "frontend/pages/course_detail_cockpit.py"
).read_text(encoding="utf-8")


def _extract_function(source: str, name: str) -> str:
    """Renvoie le corps source d'une fonction top-level jusqu'à la prochaine
    définition top-level, sans importer le module (page NiceGUI, import évité
    par convention dans les tests de ce fichier)."""
    start = source.index(f"def {name}(")
    rest = source[start:]
    candidates = [i for i in (rest.find("\ndef ", 1), rest.find("\nasync def ", 1)) if i != -1]
    end = min(candidates) if candidates else len(rest)
    return rest[:end]


def test_declared_level_block_offers_the_three_levels_and_persists_them():
    body = _extract_function(COCKPIT_SOURCE, "_render_declared_level")
    assert '"solide"' in body
    assert '"correct"' in body
    assert '"flou"' in body
    assert "knowledge_store.set_item_state" in body
    assert "review_service.invalidate_cache" in body


def test_tab_overview_renders_declared_level_between_neighbors_and_reasons():
    body = _extract_function(COCKPIT_SOURCE, "_tab_overview")
    assert "_render_declared_level(course, mastery)" in body

    neighbors_idx = body.index("Notions reliées")
    declared_idx = body.index("_render_declared_level(course, mastery)")
    reasons_idx = body.index("Pourquoi ce score")

    assert neighbors_idx < declared_idx < reasons_idx
```

- [ ] **Step 3: Run the new tests to verify they fail for the right reason**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_declared_level_cockpit.py -v`

Expected:
- `test_declared_level_block_offers_the_three_levels_and_persists_them` — FAIL/ERROR:
  `ValueError: substring not found` from `_extract_function` (`_render_declared_level` doesn't exist
  yet).
- `test_tab_overview_renders_declared_level_between_neighbors_and_reasons` — FAIL:
  `"_render_declared_level(course, mastery)" in body` is `False`.

- [ ] **Step 4: Add the function and wire it into `_tab_overview`**

In `frontend/pages/course_detail_cockpit.py`, replace:

```python
# ── Onglets ───────────────────────────────────────────────────────────────────

def _tab_overview(course, task, score, level, next_due, next_cycle,
                  mastery, sessions) -> None:
```

with:

```python
# ── Onglets ───────────────────────────────────────────────────────────────────

def _render_declared_level(course, mastery) -> None:
    from backend.core.knowledge import store as knowledge_store

    levels = (
        ("solide", "Solide", "positive"),
        ("correct", "Correct", "warning"),
        ("flou", "Flou", "negative"),
    )
    container = ui.column().classes("w-full gap-2 ci-section")

    def _render():
        state = knowledge_store.get_item_state(course.id, "college")
        container.clear()
        with container:
            with ui.row().classes("items-center gap-2"):
                ui.label("Niveau déclaré avant Synapse").classes("ci-label")
                if state is None:
                    ui.badge("À situer").props("color=grey outline")

            with ui.row().classes("items-center gap-1"):
                for level, label, color in levels:
                    selected = state is not None and state.declared_level == level

                    def _set(_level=level):
                        knowledge_store.set_item_state(
                            course.id, _level, context="college", source="triage"
                        )
                        review_service.invalidate_cache()
                        _render()

                    ui.button(label, on_click=_set).props(
                        f"unelevated rounded size=sm color={color}"
                        if selected else
                        "outline rounded size=sm color=grey"
                    )

    _render()


def _tab_overview(course, task, score, level, next_due, next_cycle,
                  mastery, sessions) -> None:
```

Then, still inside `_tab_overview`, replace:

```python
            relation_graph(
                str(course.display_item_number or course.item_number or "?"),
                _neighbor_payload(neighbor_ids),
            )

    # Raisons du score + note perso
```

with:

```python
            relation_graph(
                str(course.display_item_number or course.item_number or "?"),
                _neighbor_payload(neighbor_ids),
            )

    _render_declared_level(course, mastery)

    # Raisons du score + note perso
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_declared_level_cockpit.py -v`
Expected: both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/pages/course_detail_cockpit.py tests/test_declared_level_cockpit.py
git commit -m "feat: surface the declared-level control (Solide/Correct/Flou) in the item cockpit overview"
```

---

### Task 2: Delete the dead code in `course_detail.py`

**Files:**
- Modify: `frontend/pages/course_detail.py` (full-file rewrite — everything after the delegation to
  the cockpit is unreachable dead code, confirmed by a repo-wide grep during the design phase: no
  other file imports any symbol from this module except `course_detail_page`)
- Modify: `tests/test_knowledge_course_detail_data.py:1-14` (docstring only — no assertion changes)
- Test: `tests/test_declared_level_cockpit.py` (extended with a dead-code guard)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: nothing consumed by a later task — this is the last task in the plan.

- [ ] **Step 1: Write the failing dead-code guard test**

Append to `tests/test_declared_level_cockpit.py`:

```python
def test_course_detail_classic_has_no_leftover_dead_code():
    source = (
        Path(__file__).parents[1] / "frontend/pages/course_detail.py"
    ).read_text(encoding="utf-8")

    assert "_render_knowledge_block" not in source
    assert "_render_course_timeline" not in source
    assert "render_item_cockpit(course_id)" in source
    assert len(source.splitlines()) < 30
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_declared_level_cockpit.py::test_course_detail_classic_has_no_leftover_dead_code -v`
Expected: FAIL — `"_render_knowledge_block" not in source` is `False` (the dead code is still there).

- [ ] **Step 3: Replace the entire contents of `course_detail.py`**

Replace the full file content with:

```python
"""
course_detail.py — Synapse — Fiche Course Intelligence
-------------------------------------------------------
Route : /cours/{course_id}

Délègue entièrement à la vue cockpit (frontend/pages/course_detail_cockpit.py).
"""
from __future__ import annotations

from frontend.theme import frame


def course_detail_page(course_id: str) -> None:
    with frame("Fiche cours"):
        from frontend.pages.course_detail_cockpit import render_item_cockpit
        render_item_cockpit(course_id)
```

This drops every helper (`_fmt_date`, `_fmt_min`, `_day_ago`, `_NA_COLORS`, `_render_knowledge_block`,
`_render_course_timeline`) and every import that only served the dead branch (`datetime`, `json`,
`ui`, `logger`, `render_traps_card`, `data_store`, `local_store`, `get_course_mastery`,
`PROGRESSION_COLORS`, `get_next_action`, `ReviewTask`, `obsidian_service`, `extract_traps`,
`_settings`, `knowledge_store`, `knowledge_service`, `review_service`) — none of them are used by
the two lines that remain.

- [ ] **Step 4: Correct the now-inaccurate test docstring**

In `tests/test_knowledge_course_detail_data.py`, replace:

```python
"""Test de contrat — données affichées par le bloc « état des connaissances »
de frontend/pages/course_detail.py (_render_knowledge_block).

La couverture OIC de Task 4 est déjà testée en détail dans
tests/test_knowledge_oic.py et tests/test_knowledge_service.py. Ce test ne
revérifie pas ce calcul : il vérifie seulement la logique de gating propre au
bloc UI, à savoir la condition exacte utilisée pour décider d'afficher ou non
la ligne de couverture OIC :

    if cov["rang_a_total"] or cov["rang_b_total"]:

Si ce contrat casse, la fiche cours affiche une ligne de couverture vide (ou
en masque une qui devrait apparaître) sans aucune erreur visible.
"""
```

with:

```python
"""Test de contrat — comportement de knowledge_service.oic_coverage() pour
un item sans OIC vs. avec au moins un OIC de rang A.

Historiquement, ce test reprenait la condition de gating utilisée par le bloc
« Niveau déclaré » de la fiche cours (rang_a_total or rang_b_total) pour
décider d'afficher une ligne de couverture OIC. Ce bloc a été retiré du
cockpit au chantier C2 (2026-08-08) : la couverture OIC est affichée en
détail dans l'onglet OIC dédié (render_oic_panel), pas en résumé dans
l'onglet Vue d'ensemble. Le test reste utile comme contrat sur la forme des
comptes retournés par oic_coverage().
"""
```

The two test functions and their assertions are unchanged — only the module docstring is corrected.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_declared_level_cockpit.py tests/test_knowledge_course_detail_data.py -v`
Expected: all 5 tests PASS (2 from Task 1, 1 dead-code guard from this task, 2 unchanged from
`test_knowledge_course_detail_data.py`).

- [ ] **Step 6: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, 1152 tests (1149 baseline + 3 net new: 2 from Task 1, 1 dead-code guard from Task 2
— the docstring edit adds no test), zero regressions.

- [ ] **Step 7: Update the tracking doc**

In `docs/UI_REFONTE_ETAT_DES_LIEUX.md`, mark C2 as terminé (commit hashes, tests before → after) in
the same table format used for A/B1-B4/C1, and update the "▶ REPRISE" header to point at the next
open sub-chantier (C3, C4, C5, or D — whichever is picked next). This file stays uncommitted, per
the established convention for this series of chantiers.

- [ ] **Step 8: Commit**

```bash
git add frontend/pages/course_detail.py tests/test_declared_level_cockpit.py tests/test_knowledge_course_detail_data.py
git commit -m "refactor: delete unreachable dead code in course_detail.py now that its only live UI moved to the cockpit"
```

---

## Self-Review Notes

- **Spec coverage:** §1 (new `_render_declared_level`) → Task 1 Step 4. §2 (wiring into
  `_tab_overview`, placement between neighbors and reasons) → Task 1 Step 4 (second replacement) +
  Task 1 Step 2 (order assertion). §3 (dead-code deletion in `course_detail.py`) → Task 2 Step 3.
  Test docstring accuracy risk noted in the spec's Risks section → Task 2 Step 4.
- **Placeholder scan:** none found — every step has literal code, exact commands, exact expected
  output.
- **Type/name consistency:** `_render_declared_level(course, mastery)` is used identically in its
  definition (Task 1 Step 4), its call site (Task 1 Step 4), and both tests that reference it (Task 1
  Step 2).
- **Bug caught during self-review, fixed inline:** the spec's snippet defined the three levels as a
  module-level `_DECLARED_LEVELS` constant sitting *before* `_render_declared_level`. Since
  `_extract_function()` (Task 1 Step 2) captures a function body starting at `def name(`, a
  module-level constant defined above the function is never included in the extracted text — the
  `'"solide"' in body` assertions would have failed even after a correct implementation, because
  those literals would live outside the captured span. Fixed by moving the three-tuple to a local
  `levels = (...)` variable inside the function body, where the scoped test can actually see it. No
  other behavior changes; the spec's intent (three fixed levels, same labels/colors) is preserved.
- **Task boundary check:** Task 1 and Task 2 are independently reviewable and independently
  testable — a reviewer could approve the new cockpit control (Task 1) while asking for more time on
  the dead-code deletion (Task 2), or vice versa. Task 2 doesn't depend on any symbol Task 1
  introduces (it only deletes code in a different file and corrects a docstring), so the two could
  even be reordered, though doing the port first is the logical sequence given the spec's narrative.
