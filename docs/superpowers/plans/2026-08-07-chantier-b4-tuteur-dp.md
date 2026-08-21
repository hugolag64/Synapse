# Chantier B4 — Déplacement structurel du Tuteur DP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the "Tuteur DP" block out of the Historique tab and into the QCM tab of
`frontend/pages/course_detail_cockpit.py`, next to the Série QCM adaptative block, and replace its
decorative `indigo` Quasar color with `primary` / the shared `.ci-reco` design-system class.

**Architecture:** Extract the block into a new private function `_render_dp_tutor(course, lacunes)`,
defined immediately before `_tab_qcm` (its only caller). Call it from `_tab_qcm` right after the QCM
summary and before the Série adaptative block (not after — the Série adaptative block has an early
`return` when there are no recurring gaps, which would otherwise hide the Tuteur DP for those items).
Delete the equivalent block from `_tab_history`.

**Tech Stack:** NiceGUI (`ui.column`/`ui.button`), pytest (source-text assertions, no module import —
matches the existing test style for this file).

## Global Constraints

- No new function parameters: `_render_dp_tutor` takes exactly `(course, lacunes)`, both already
  available as parameters of `_tab_qcm`.
- `_tab_history(course, sessions, qcm_sessions, lacunes, review_hist)` signature stays unchanged.
- The two `color=indigo` Quasar button props become `color=primary`. No other `indigo` usage in the
  file is touched (line 562 podcast spinner, line 726 "+ Mnémo/Image" button, line 1035/1171 icon
  accents are all out of scope).
- The block's container becomes `.ci-reco` / `.ci-reco-meta` (already defined in this file at line
  141) — no new CSS rule is added.
- Full suite (`./.venv/Scripts/python.exe -m pytest -q`) run before Step 1 and after the last step,
  zero regressions.

---

### Task 1: Move `_render_dp_tutor` from Historique to QCM and drop `indigo`

**Files:**
- Modify: `frontend/pages/course_detail_cockpit.py:884` (insert new function before `_tab_qcm`)
- Modify: `frontend/pages/course_detail_cockpit.py:897-907` (call the new function inside `_tab_qcm`)
- Modify: `frontend/pages/course_detail_cockpit.py:1107-1142` (delete the old inline block from
  `_tab_history`)
- Test: `tests/test_dp_tutor.py`

**Interfaces:**
- Consumes: `course` (has `.item_number`, `.display_item_number`, `.id`, `.title`), `lacunes` (list
  of row-like objects readable via the existing `_row_get(row, key, default=None)` helper already
  defined earlier in `course_detail_cockpit.py`), `local_store.get_ai_practice_history(item_number,
  limit)` and `render_dp_tutor_action(item_number, dp_session, errors, gap_details, refresh)` — both
  already imported at the top of the file (lines 27 and 57).
- Produces: `_render_dp_tutor(course, lacunes) -> None`, a private module-level function callable
  from `_tab_qcm`. No other task depends on this — it's the only task in this plan.

- [ ] **Step 1: Run the full suite to record the baseline**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS. Note the total test count — Step 5 compares against it (expect baseline + 2, since
Step 2 replaces 2 existing tests in `test_dp_tutor.py` with 4).

- [ ] **Step 2: Write the failing tests**

Replace `tests/test_dp_tutor.py` in full with:

```python
import json
from pathlib import Path
from types import SimpleNamespace

from backend.core.ai.routing import AIModel, AIResponse
from backend.core.practice.models import PracticeKind
from backend.core.practice.service import PracticeService

COCKPIT_SOURCE = (
    Path(__file__).parents[1] / "frontend/pages/course_detail_cockpit.py"
).read_text(encoding="utf-8")


def _extract_function(source: str, name: str) -> str:
    """Renvoie le corps source d'une fonction top-level jusqu'à la prochaine
    définition top-level, sans importer le module (page NiceGUI, import évité
    par convention dans ce fichier de tests)."""
    start = source.index(f"def {name}(")
    rest = source[start:]
    candidates = [i for i in (rest.find("\ndef ", 1), rest.find("\nasync def ", 1)) if i != -1]
    end = min(candidates) if candidates else len(rest)
    return rest[:end]


def test_item_qcm_exposes_tutor_dp_action():
    assert "render_dp_tutor_action" in COCKPIT_SOURCE
    tab_qcm_body = _extract_function(COCKPIT_SOURCE, "_tab_qcm")
    assert "_render_dp_tutor(course, lacunes)" in tab_qcm_body


def test_item_history_no_longer_renders_tutor_dp():
    history_body = _extract_function(COCKPIT_SOURCE, "_tab_history")
    assert "TUTEUR DP" not in history_body
    assert "_render_dp_tutor" not in history_body


def test_tutor_dp_block_uses_primary_color_and_shared_reco_style():
    tutor_body = _extract_function(COCKPIT_SOURCE, "_render_dp_tutor")
    assert "color=indigo" not in tutor_body
    assert tutor_body.count("color=primary") == 2
    assert "ci-reco" in tutor_body


def test_dp_tutor_context_is_explicit_and_session_is_dp():
    class FakeAI:
        def __init__(self):
            self.context = None

        def generate(self, task, prompt, *, context=None, response_format="text"):
            self.context = context
            payload = {
                "questions": [
                    {"kind": "closed", "prompt": "Q", "choices": ["A", "B"], "answer": "A", "explanation": "E"}
                ]
            }
            return AIResponse(json.dumps(payload), AIModel.FLASH, 1, 1)

    fake = FakeAI()
    store = SimpleNamespace(create_ai_practice_session=lambda **kwargs: kwargs["spec"].practice_kind.value)
    service = PracticeService(ai_service=fake, store=store)

    session_id = service.create_tutor_dp_session(
        item_number="221",
        course_id="course-221",
        course_title="Méningite",
        dossier_context="Patient fébrile avec purpura.",
        errors=[{"category": "rang_a", "detail": "antibiotique retardé"}],
        gap_details=["Urgence thérapeutique"],
        total_questions=1,
    )

    assert session_id == PracticeKind.DP.value
    assert "Patient fébrile" in fake.context
    assert "rang_a" in fake.context
    assert "Urgence thérapeutique" in fake.context
```

This replaces the old `test_item_history_exposes_tutor_dp_action` (which asserted the block lived
in `_tab_history`) with three tests scoped to the new expected shape, and keeps the untouched
backend test `test_dp_tutor_context_is_explicit_and_session_is_dp` as-is.

- [ ] **Step 3: Run the new tests to verify they fail for the right reason**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_dp_tutor.py -v`

Expected:
- `test_item_qcm_exposes_tutor_dp_action` — FAIL: `"_render_dp_tutor(course, lacunes)" in tab_qcm_body` is `False` (the call doesn't exist yet in `_tab_qcm`).
- `test_item_history_no_longer_renders_tutor_dp` — FAIL: `"TUTEUR DP" not in history_body` is `False` (the block is still in `_tab_history`).
- `test_tutor_dp_block_uses_primary_color_and_shared_reco_style` — FAIL/ERROR: `ValueError: substring not found` from `_extract_function` (`_render_dp_tutor` doesn't exist yet in the source).
- `test_dp_tutor_context_is_explicit_and_session_is_dp` — PASS (untouched backend behavior).

- [ ] **Step 4: Insert `_render_dp_tutor`, wire it into `_tab_qcm`, delete it from `_tab_history`**

In `frontend/pages/course_detail_cockpit.py`, replace:

```python
def _tab_qcm(course, qcm_summary, qcm_sessions, lacunes, mastery_score=None) -> None:
    render_ai_practice_panel(course, mastery_score=mastery_score)
```

with:

```python
def _render_dp_tutor(course, lacunes) -> None:
    item_number = str(getattr(course, "item_number", "") or getattr(course, "display_item_number", "") or "")
    ai_history = local_store.get_ai_practice_history(item_number=item_number, limit=30) if item_number else []
    dp_history = [entry for entry in ai_history if str(entry["session"].get("practice_kind", "")).lower() == "dp"]
    errors = [
        {"category": _row_get(l, "category") or "non_classe", "detail": _row_get(l, "detail") or ""}
        for l in lacunes
    ]
    gap_details = [str(_row_get(l, "detail") or "") for l in lacunes]
    with ui.column().classes("w-full gap-2 ci-reco"):
        ui.label("TUTEUR DP").classes("ci-reco-meta")
        if dp_history:
            for entry in dp_history[:5]:
                session = entry["session"]
                questions = entry.get("questions", [])
                dossier_context = "\n".join(str(q.get("prompt") or "") for q in questions[:5])
                ui.button(
                    f"Ouvrir le Tuteur DP · Session #{session['id']}",
                    on_click=lambda session=session, dossier_context=dossier_context: render_dp_tutor_action(
                        item_number=item_number,
                        dp_session={**session, "dossier_context": dossier_context, "course_id": course.id, "course_title": course.title},
                        errors=errors,
                        gap_details=gap_details,
                        refresh=lambda: None,
                    ),
                ).props("flat color=primary align=left")
        else:
            ui.button(
                "Ouvrir le Tuteur DP sur cet Item",
                on_click=lambda: render_dp_tutor_action(
                    item_number=item_number,
                    dp_session={"course_id": course.id, "course_title": course.title, "dossier_context": ""},
                    errors=errors,
                    gap_details=gap_details,
                    refresh=lambda: None,
                ),
            ).props("unelevated color=primary")


def _tab_qcm(course, qcm_summary, qcm_sessions, lacunes, mastery_score=None) -> None:
    render_ai_practice_panel(course, mastery_score=mastery_score)
```

Then, still inside `_tab_qcm`, replace:

```python
    if not qcm_summary.get("count"):
        ui.label("Aucune session QCM enregistrée pour cet item.").classes("ci-empty")
    else:
        last = qcm_summary.get("last_score")
        with ui.element("div").classes("ci-section"):
            for label, val in (("Dernier QCM", last), ("Moyenne", qcm_summary["avg_score"])):
                with ui.element("div").classes("ci-bar-row"):
                    ui.label(label).classes("ci-bar-label")
                    mastery_indicator(int(val) if val is not None else None)

    # Série adaptative : dérivée des lacunes récurrentes réelles
```

with:

```python
    if not qcm_summary.get("count"):
        ui.label("Aucune session QCM enregistrée pour cet item.").classes("ci-empty")
    else:
        last = qcm_summary.get("last_score")
        with ui.element("div").classes("ci-section"):
            for label, val in (("Dernier QCM", last), ("Moyenne", qcm_summary["avg_score"])):
                with ui.element("div").classes("ci-bar-row"):
                    ui.label(label).classes("ci-bar-label")
                    mastery_indicator(int(val) if val is not None else None)

    _render_dp_tutor(course, lacunes)

    # Série adaptative : dérivée des lacunes récurrentes réelles
```

Finally, in `_tab_history`, delete the now-duplicated block entirely — replace:

```python
    item_number = str(getattr(course, "item_number", "") or getattr(course, "display_item_number", "") or "")
    ai_history = local_store.get_ai_practice_history(item_number=item_number, limit=30) if item_number else []
    dp_history = [entry for entry in ai_history if str(entry["session"].get("practice_kind", "")).lower() == "dp"]
    errors = [
        {"category": _row_get(l, "category") or "non_classe", "detail": _row_get(l, "detail") or ""}
        for l in lacunes
    ]
    gap_details = [str(_row_get(l, "detail") or "") for l in lacunes]
    with ui.column().classes("w-full gap-2 mt-5 p-4 rounded-xl border border-indigo-200 dark:border-indigo-900 bg-indigo-50/40 dark:bg-indigo-950/20"):
        ui.label("TUTEUR DP").classes("text-[10px] font-mono uppercase tracking-widest text-indigo-500 font-semibold")
        if dp_history:
            for entry in dp_history[:5]:
                session = entry["session"]
                questions = entry.get("questions", [])
                dossier_context = "\n".join(str(q.get("prompt") or "") for q in questions[:5])
                ui.button(
                    f"Ouvrir le Tuteur DP · Session #{session['id']}",
                    on_click=lambda session=session, dossier_context=dossier_context: render_dp_tutor_action(
                        item_number=item_number,
                        dp_session={**session, "dossier_context": dossier_context, "course_id": course.id, "course_title": course.title},
                        errors=errors,
                        gap_details=gap_details,
                        refresh=lambda: None,
                    ),
                ).props("flat color=indigo align=left")
        else:
            ui.button(
                "Ouvrir le Tuteur DP sur cet Item",
                on_click=lambda: render_dp_tutor_action(
                    item_number=item_number,
                    dp_session={"course_id": course.id, "course_title": course.title, "dossier_context": ""},
                    errors=errors,
                    gap_details=gap_details,
                    refresh=lambda: None,
                ),
            ).props("unelevated color=indigo")


```

with nothing (delete it), so that `_tab_history` ends right after the `ACTIVITÉ RÉCENTE` loop and
the module continues with `async def _load_podcast_tab(...)`. After deleting, check the blank-line
count between the two: collapse to exactly one blank line if the deletion left two or more (matches
the single-blank-line spacing used between every other top-level function in this file) — purely
cosmetic, has no effect on the tests.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_dp_tutor.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 6: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, same total count as the Step 1 baseline plus the net new tests in
`test_dp_tutor.py` (4 tests now instead of 2 → +2), zero regressions elsewhere.

- [ ] **Step 7: Update the tracking doc**

In `docs/UI_REFONTE_ETAT_DES_LIEUX.md`, mark B4 as terminé (commit hash, tests before → after) in
the same table format used for A/B1/B2/B3, and update the "▶ REPRISE" header to point at chantiers
C/D as the next open work (per section 5 of that doc). This file stays uncommitted, per the
established convention for this series of chantiers.

- [ ] **Step 8: Commit**

```bash
git add frontend/pages/course_detail_cockpit.py tests/test_dp_tutor.py
git commit -m "refactor: move Tuteur DP from Historique tab to QCM tab, indigo to primary"
```

---

## Self-Review Notes

- **Spec coverage:** §1 (extraction into `_render_dp_tutor`) → Step 4. §2 (removal from
  `_tab_history`) → Step 4 (final replacement). §3 (call site placement before Série adaptative,
  avoiding the premature `return`) → Step 4 (call inserted before the `# Série adaptative` comment).
  Tests section of the spec → Step 2 (all three prescribed tests written, using text-slicing instead
  of `inspect.getsource` — see deviation note below).
- **Deviation from spec, justified:** the spec's Risks section suggested scoping the indigo check via
  `inspect.getsource(_render_dp_tutor)`, which requires importing `course_detail_cockpit.py` as a
  module. Every existing test that targets this specific file (`test_b1_wrap_widths.py`,
  `test_course_detail_responsive.py`, the original `test_dp_tutor.py`) reads it as raw text via
  `Path.read_text()` instead — this file is never imported directly in tests. `_extract_function()`
  reproduces the same scoping guarantee (bounded to one function's body, not a whole-file grep)
  without breaking that established convention.
- **Placeholder scan:** none found — every step has literal code, exact run commands, and exact
  expected output.
- **Type/name consistency:** `_render_dp_tutor(course, lacunes)` is the only new symbol introduced;
  its name and signature are identical everywhere it's referenced (definition, call site, all three
  new tests).
