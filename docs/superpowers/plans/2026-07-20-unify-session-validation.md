# Unify Session Validation Flows — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every review type (J3/J7/J14/J30/bonus/qcm_error/manuel/consolidation), across Dashboard, Mode Focus, and Planning, validate through the same primary action — the full "Retour de séance" dialog — with the same secondary actions (confiance rapide, Passer, Lacune, PDF/Fiche EDN), and collapse the three duplicate row/card renderers down to one shared component reused by planning.py.

**Architecture:** `render_review_row` (`frontend/pages/dashboard/_reviews.py`) becomes the single canonical row component for every list view, including planning.py's Consolidation tab (replacing the bespoke `_consolidation_card`). `render_review_card` (Focus mode) keeps its own larger layout but adopts the same button behavior. The consolidation-completion write path (`mark_consolidation_done` + `add_study_session`) is extracted once into `backend/core/reviews/consolidation.py` so dashboard and planning.py stop duplicating it.

**Tech Stack:** Python 3.13, NiceGUI 3.8.0, SQLite (via `backend/core/reviews/local_store.py`), pytest 9.0.3 (run with `"/c/Users/hugol/AppData/Local/Programs/Python/Python313/python.exe" -m pytest`, NOT the project's `.venv` — pytest isn't installed there).

## Global Constraints

- No automated UI tests exist for NiceGUI pages in this repo — verification of frontend tasks is manual (restart the app, click through). Do not attempt to invent NiceGUI test scaffolding; follow the existing project convention.
- Hot-reload has proven unreliable for verifying dashboard/consolidation changes in this project — always do a full restart (`Ctrl+C` then `python main.py`) before manually verifying a frontend task.
- Backend logic changes (Task 1) get real pytest coverage, following the existing pattern in `tests/test_consolidation.py` (module-level `isolated_db` autouse fixture monkeypatching `ls.DB_PATH`).
- Keep `render_review_card`'s and `render_review_row`'s public call signatures backward compatible with all existing callers except the ones this plan explicitly updates (`planning.py`).
- French UI copy throughout (labels, tooltips, notifications) — match the existing tone (see current strings in `_reviews.py` / `_dialogs.py`).

---

### Task 1: Extract shared consolidation-completion logic

**Files:**
- Modify: `backend/core/reviews/consolidation.py`
- Test: `tests/test_consolidation.py`

**Interfaces:**
- Produces: `complete_consolidation_task(task: ReviewTask, activity_types=None, duration_minutes=None, confidence=None, difficulty=None, qcm_result=None, weak_category=None, weak_detail=None) -> None` — advances the SM-2 chain (`local_store.mark_consolidation_done`) and logs the work session (`local_store.add_study_session`) in one call. Later tasks (2, 6) call this instead of duplicating the two `local_store` calls.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_consolidation.py` (the file already imports `datetime`, `pytest`, and has `ls` = `backend.core.reviews.local_store` available at module scope, plus the autouse `isolated_db` fixture):

```python
# ── complete_consolidation_task ──────────────────────────────────────────────

def _make_consolidation_task(
    course_id="course-1", context="college", due=datetime.date(2026, 1, 1),
):
    from backend.core.reviews.models import ReviewTask
    return ReviewTask(
        id=f"{course_id}_{context}_consolidation_{due.isoformat()}",
        course_id=course_id,
        course_title="Cardiopathies",
        item_number="234",
        college=["Cardiologie"],
        context=context,
        theoretical_due_date=due,
        due_date=due,
        review_type="consolidation",
        status="todo",
    )


def test_complete_consolidation_task_avance_la_chaine_sm2():
    from backend.core.reviews.consolidation import complete_consolidation_task
    task = _make_consolidation_task()
    complete_consolidation_task(task, confidence=4, difficulty="facile")
    state = ls.get_last_consolidation_state("course-1", "college")
    assert state is not None
    assert state["repetition_count"] == 1


def test_complete_consolidation_task_logue_une_session():
    from backend.core.reviews.consolidation import complete_consolidation_task
    task = _make_consolidation_task()
    complete_consolidation_task(
        task, activity_types=["révision", "qcm"], duration_minutes=25,
        confidence=4, difficulty="facile", qcm_result="réussi",
    )
    sessions = ls.get_recent_study_sessions(limit=5)
    assert len(sessions) == 1
    assert sessions[0]["course_id"] == "course-1"
    assert sessions[0]["duration_minutes"] == 25
    assert sessions[0]["qcm_result"] == "réussi"


def test_complete_consolidation_task_defaut_confiance_3_si_absente():
    from backend.core.reviews.consolidation import complete_consolidation_task
    task = _make_consolidation_task()
    complete_consolidation_task(task)  # aucune confidence fournie
    state = ls.get_last_consolidation_state("course-1", "college")
    assert state["repetition_count"] == 1
    sessions = ls.get_recent_study_sessions(limit=5)
    assert sessions[0]["activity_types"] == '["révision"]'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `"/c/Users/hugol/AppData/Local/Programs/Python/Python313/python.exe" -m pytest tests/test_consolidation.py -k complete_consolidation_task -v`
Expected: 3 FAIL with `ImportError: cannot import name 'complete_consolidation_task'`

- [ ] **Step 3: Implement `complete_consolidation_task`**

Add to `backend/core/reviews/consolidation.py`, after `get_or_bootstrap_task` (end of file):

```python
def complete_consolidation_task(
    task: ReviewTask,
    activity_types: Optional[list] = None,
    duration_minutes: Optional[int] = None,
    confidence: Optional[int] = None,
    difficulty: Optional[str] = None,
    qcm_result: Optional[str] = None,
    weak_category: Optional[str] = None,
    weak_detail: Optional[str] = None,
) -> None:
    """
    Valide une occurrence 'consolidation' : avance la chaîne SM-2 et logue la
    séance de travail associée. Point d'entrée unique utilisé par le dashboard
    et par planning.py — évite de dupliquer ces deux appels local_store à deux
    endroits.
    """
    local_store.mark_consolidation_done(
        course_id=task.course_id,
        context=task.context,
        theoretical_due_date=task.theoretical_due_date,
        course_title=task.course_title,
        item_number=task.item_number or "",
        confidence=confidence or 3,
        difficulty=difficulty,
    )
    local_store.add_study_session(
        course_id=task.course_id,
        course_title=task.course_title,
        item_number=task.item_number or "",
        context=task.context,
        activity_types=activity_types or ["révision"],
        duration_minutes=duration_minutes,
        confidence=confidence,
        difficulty=difficulty,
        qcm_result=qcm_result,
        weak_category=weak_category,
        weak_detail=weak_detail,
    )
```

No new imports needed — `local_store` and `ReviewTask` are already imported at the top of `consolidation.py`, and `Optional` is already imported from `typing`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `"/c/Users/hugol/AppData/Local/Programs/Python/Python313/python.exe" -m pytest tests/test_consolidation.py -v`
Expected: all tests in the file PASS (previous tests + the 3 new ones)

- [ ] **Step 5: Commit**

```bash
git add backend/core/reviews/consolidation.py tests/test_consolidation.py
git commit -m "feat(reviews): extract complete_consolidation_task to remove dashboard/planning duplication"
```

---

### Task 2: Add `initial_duration_minutes` to the session-feedback dialog

**Files:**
- Modify: `frontend/pages/dashboard/_dialogs.py:205-218` (function `open_session_feedback_dialog`)

**Interfaces:**
- Consumes: nothing new.
- Produces: `open_session_feedback_dialog(task, card, validate_fn, initial_duration_minutes: int | None = None)` — when `initial_duration_minutes` is given, the dialog's duration state starts at that value instead of the type-based default. Task 5 (Focus mode) calls this with the chrono's elapsed minutes.

- [ ] **Step 1: Modify the function signature and default-duration logic**

In `frontend/pages/dashboard/_dialogs.py`, change:

```python
def open_session_feedback_dialog(
    task: ReviewTask,
    card,
    validate_fn,
) -> None:
    """Modale 'Retour de séance' avec chips multi-sélection."""
    if task.review_type == "bonus":
        _acts, _dur, _conf, _diff, _qcm = ["lecture"], 30, 3, "moyen", None
    elif task.review_type == "qcm_error":
        _acts, _dur, _conf, _diff, _qcm = ["qcm", "correction"], 20, 2, "difficile", "raté"
    elif task.review_type == "lacune":
        _acts, _dur, _conf, _diff, _qcm = ["correction"], 15, 3, "moyen", None
    else:
        _acts, _dur, _conf, _diff, _qcm = ["révision"], 20, 3, "moyen", None
```

to:

```python
def open_session_feedback_dialog(
    task: ReviewTask,
    card,
    validate_fn,
    initial_duration_minutes: int | None = None,
) -> None:
    """Modale 'Retour de séance' avec chips multi-sélection."""
    if task.review_type == "bonus":
        _acts, _dur, _conf, _diff, _qcm = ["lecture"], 30, 3, "moyen", None
    elif task.review_type == "qcm_error":
        _acts, _dur, _conf, _diff, _qcm = ["qcm", "correction"], 20, 2, "difficile", "raté"
    elif task.review_type == "lacune":
        _acts, _dur, _conf, _diff, _qcm = ["correction"], 15, 3, "moyen", None
    else:
        _acts, _dur, _conf, _diff, _qcm = ["révision"], 20, 3, "moyen", None

    if initial_duration_minutes is not None:
        _dur = max(1, int(initial_duration_minutes))
```

- [ ] **Step 2: Pre-fill the custom duration input when the value isn't a preset**

Find this block further down in the same function (currently around line 302-306):

```python
                    with ui.element("div").classes("flex items-center gap-1 ml-1"):
                        custom_dur = ui.number(min=1, max=300, placeholder="···").classes("w-12").props(
                            "dense borderless"
                        )
                        ui.label("min").classes("text-xs text-slate-400 pb-0.5")
```

Replace with:

```python
                    with ui.element("div").classes("flex items-center gap-1 ml-1"):
                        custom_dur = ui.number(
                            min=1, max=300, placeholder="···",
                            value=(state_fb.duration if state_fb.duration not in DUR_PRESETS else None),
                        ).classes("w-12").props("dense borderless")
                        ui.label("min").classes("text-xs text-slate-400 pb-0.5")
```

(`DUR_PRESETS` is already defined earlier in the function as `[5, 10, 20, 30, 45, 60, 90]`.)

- [ ] **Step 3: Manual verification**

Restart the app (`Ctrl+C` then `python main.py`). This function isn't reachable with a non-default `initial_duration_minutes` until Task 5 wires the caller, so for now just confirm the app boots without errors and any existing "Détailler…"/consolidation Valider flow still opens the dialog normally with default duration.

- [ ] **Step 4: Commit**

```bash
git add frontend/pages/dashboard/_dialogs.py
git commit -m "feat(dashboard): support pre-filled duration in session feedback dialog"
```

---

### Task 3: `render_review_row` — unify the primary action for every review type

**Files:**
- Modify: `frontend/pages/dashboard/_reviews.py:246-320`

**Interfaces:**
- Consumes: `open_session_feedback_dialog` (unchanged signature usage here — no `initial_duration_minutes` needed for rows, only Focus mode uses it).
- Produces: no signature change to `render_review_row` itself — same `(container, task, on_done, on_postpone, on_ignore, qcm_info, lacune_count, validate_fn, on_lacune_saved, is_overdue)`. Behavior change only.

- [ ] **Step 1: Replace the branching Valider button with one unconditional block**

In `render_review_row`, replace:

```python
            # Bouton Valider
            if task.review_type == "consolidation":
                ui.button(icon="check_circle").props(
                    "flat round dense size=sm color=cyan aria-label='Valider'"
                ).classes("shrink-0").on_click(
                    lambda t=task, el=row_el: open_session_feedback_dialog(t, el, validate_fn)
                ).tooltip("Valider (détails)")

                if on_postpone:
                    def _make_pass(t=task, el=row_el):
                        async def _h():
                            await on_postpone(t, el, 7)
                        return _h

                    ui.button(icon="skip_next").props(
                        "flat round dense size=sm color=slate aria-label='Passer'"
                    ).classes("shrink-0").on_click(_make_pass()).tooltip("Passer (7 jours)")
            else:
                def _make_val(t=task, el=row_el):
                    async def _h():
                        await on_done(t, el, ["révision"], na.duration_min, 3, "moyen")
                    return _h

                ui.button(icon="check_circle").props(
                    "flat round dense size=sm color=green aria-label='Valider'"
                ).classes("shrink-0").on_click(_make_val()).tooltip("Valider (confiance moyenne)")
```

with:

```python
            # Bouton Valider — ouvre toujours le dialog complet, pour tous les types
            ui.button(icon="check_circle").props(
                "flat round dense size=sm color=cyan aria-label='Valider'"
            ).classes("shrink-0").on_click(
                lambda t=task, el=row_el: open_session_feedback_dialog(t, el, validate_fn)
            ).tooltip("Valider (détails)")

            if on_postpone:
                def _make_pass(t=task, el=row_el):
                    async def _h():
                        await on_postpone(t, el, 7)
                    return _h

                ui.button(icon="skip_next").props(
                    "flat round dense size=sm color=slate aria-label='Passer'"
                ).classes("shrink-0").on_click(_make_pass()).tooltip("Passer (7 jours)")
```

`na` is still used elsewhere in the function (the duration label) so leave its computation untouched — only the direct-validate call that used `na.duration_min` is removed.

- [ ] **Step 2: Remove the now-redundant "Détailler…" menu item**

In the same function's "⋯" menu, find:

```python
                    ui.separator()

                    ui.menu_item(
                        "Détailler…",
                        on_click=lambda t=task, el=row_el: open_session_feedback_dialog(t, el, validate_fn),
                    ).classes("text-xs text-slate-500 font-medium")

                    ui.menu_item(
                        "Lacune…",
                        on_click=lambda t=task, r=on_lacune_saved: open_lacune_inline_dialog(t, on_save=r),
                    ).classes("text-xs text-amber-600 font-medium")
```

Replace with:

```python
                    ui.separator()

                    ui.menu_item(
                        "Lacune…",
                        on_click=lambda t=task, r=on_lacune_saved: open_lacune_inline_dialog(t, on_save=r),
                    ).classes("text-xs text-amber-600 font-medium")
```

- [ ] **Step 3: Manual verification**

Restart the app. On the Dashboard, in the RETARD/AUJOURD'HUI list:
- Click ✓ on a J3/J7/J14/J30/bonus/qcm_error/manuel item → the "Retour de séance" dialog opens (previously: instant validation, no dialog).
- Click ⏭ (skip_next icon) on the same item → it's reported 7 days out (previously: this icon only existed for consolidation rows).
- Click ✓ on a consolidation item → same dialog opens (unchanged from before).
- Open "⋯" on any item → "Détailler…" is gone, "Lacune…" is the first item after the confidence-emoji block.

- [ ] **Step 4: Commit**

```bash
git add frontend/pages/dashboard/_reviews.py
git commit -m "feat(dashboard): unify review-row Valider button to always open the feedback dialog"
```

---

### Task 4: Wire `dashboard/__init__.py::_on_done` to the shared consolidation helper

**Files:**
- Modify: `frontend/pages/dashboard/__init__.py:160-196`

**Interfaces:**
- Consumes: `complete_consolidation_task` from Task 1 (`backend.core.reviews.consolidation`).
- Produces: no change to `_on_done`'s own signature or its callers.

- [ ] **Step 1: Replace the consolidation branch + shared `add_study_session` call**

Currently:

```python
            if task.review_type == "consolidation":
                local_store.mark_consolidation_done(
                    course_id=task.course_id,
                    context=task.context,
                    theoretical_due_date=task.theoretical_due_date,
                    course_title=task.course_title,
                    item_number=task.item_number or "",
                    confidence=confidence or 3,
                    difficulty=difficulty,
                )
            else:
                local_store.mark_done(
                    task_id=task.id,
                    course_id=task.course_id,
                    context=task.context,
                    review_type=task.review_type,
                    theoretical_due_date=task.theoretical_due_date,
                    course_title=task.course_title,
                    item_number=task.item_number or "",
                    difficulty=difficulty,
                    confidence=confidence,
                )
            state.done_today_count += 1

            local_store.add_study_session(
                course_id=task.course_id,
                course_title=task.course_title,
                item_number=task.item_number or "",
                context=task.context,
                activity_types=activity_types or ["révision"],
                duration_minutes=duration_minutes,
                confidence=confidence,
                difficulty=difficulty,
                qcm_result=qcm_result,
                weak_category=weak_category,
                weak_detail=weak_detail,
            )
```

Replace with:

```python
            if task.review_type == "consolidation":
                from backend.core.reviews.consolidation import complete_consolidation_task
                complete_consolidation_task(
                    task,
                    activity_types=activity_types,
                    duration_minutes=duration_minutes,
                    confidence=confidence,
                    difficulty=difficulty,
                    qcm_result=qcm_result,
                    weak_category=weak_category,
                    weak_detail=weak_detail,
                )
            else:
                local_store.mark_done(
                    task_id=task.id,
                    course_id=task.course_id,
                    context=task.context,
                    review_type=task.review_type,
                    theoretical_due_date=task.theoretical_due_date,
                    course_title=task.course_title,
                    item_number=task.item_number or "",
                    difficulty=difficulty,
                    confidence=confidence,
                )
                local_store.add_study_session(
                    course_id=task.course_id,
                    course_title=task.course_title,
                    item_number=task.item_number or "",
                    context=task.context,
                    activity_types=activity_types or ["révision"],
                    duration_minutes=duration_minutes,
                    confidence=confidence,
                    difficulty=difficulty,
                    qcm_result=qcm_result,
                    weak_category=weak_category,
                    weak_detail=weak_detail,
                )
            state.done_today_count += 1
```

(`add_study_session` now only runs in the `else` branch because `complete_consolidation_task` already logs the session for consolidation — calling it again here would double-log.)

- [ ] **Step 2: Manual verification**

Restart the app. On the Dashboard, validate one consolidation item and one J-cycle item via the dialog. Check `local_store.get_recent_study_sessions()` — e.g. via a throwaway `python -c` snippet against the real DB, or just confirm in the UI that `/stats` "Cette semaine" count increments by exactly 1 per validation, not 2.

- [ ] **Step 3: Commit**

```bash
git add frontend/pages/dashboard/__init__.py
git commit -m "refactor(dashboard): route consolidation completion through complete_consolidation_task"
```

---

### Task 5: `render_review_card` (Mode Focus) — same unification + chrono duration handoff

**Files:**
- Modify: `frontend/pages/dashboard/_reviews.py:582-723`

**Interfaces:**
- Consumes: `open_session_feedback_dialog(task, card, validate_fn, initial_duration_minutes=None)` from Task 2.
- Produces: no change to `render_review_card`'s own signature.

- [ ] **Step 1: Replace the 1-click Valider + tune-menu block**

Current code (the whole "Actions" row body from the chrono button through the end of the tune menu's "Lacune..." item):

```python
                    ui.button("⏱").props("flat round dense size=xs").classes(
                        "text-slate-300 hover:text-orange-500 shrink-0"
                    ).tooltip("Chronométrer (auto-remplit la durée)").on_click(_toggle_timer)

                    # UX-02 — Bouton 1-clic "✓ Valider"
                    def _make_direct_val(t, c, _ts=_tstate):
                        async def _h():
                            _dur = 20
                            if _ts["t0"] is not None:
                                _dur = max(1, int(
                                    (datetime.datetime.now() - _ts["t0"]).total_seconds() / 60
                                ))
                            await on_done(t, c, ["révision"], _dur, 3, "moyen")
                        return _h

                    ui.button("Valider").props(
                        "unelevated rounded dense size=sm color=green-6"
                        " aria-label='Valider la révision'"
                    ).classes("text-[11px] font-bold px-3").on_click(
                        _make_direct_val(task, card)
                    ).tooltip("Valider rapidement (confiance moyenne)")

                    with ui.button(icon="tune").props(
                        "flat round dense size=sm color=green aria-label='Feedback détaillé'"
                    ).tooltip("Valider avec feedback détaillé"):
                        with ui.menu() as _val_menu:
                            _CONF_EMOJIS = [
                                (1, "😰", "red",   "Très difficile"),
                                (2, "😟", "orange","Difficile"),
                                (3, "😐", "blue",  "Moyen"),
                                (4, "😊", "teal",  "Facile"),
                                (5, "🔥", "green", "Parfait !"),
                            ]
                            _TYPE_DUR_BASE = {
                                "J3": 15, "J7": 20, "J14": 25, "J30": 30,
                                "bonus": 30, "qcm_error": 20, "manuel": 20,
                            }
                            _base_dur = _TYPE_DUR_BASE.get(task.review_type, 20)

                            def _make_quick_val(score, t, c, menu, base):
                                _score_map = {
                                    1: (max(base, 30), "difficile"),
                                    2: (max(base, 25), "difficile"),
                                    3: (base,          "moyen"),
                                    4: (min(base, 15), "facile"),
                                    5: (10,            "facile"),
                                }
                                _dur, _diff = _score_map[score]
                                async def _h():
                                    menu.close()
                                    await on_done(t, c, ["révision"], _dur, score, _diff)
                                return _h

                            with ui.element("div").classes("px-3 pt-3 pb-2 flex flex-col gap-2"):
                                ui.label("Confiance ?").classes(
                                    "text-[11px] font-bold text-slate-400 uppercase tracking-wide"
                                )
                                with ui.row().classes("gap-1 justify-center mt-1"):
                                    for _score, _emoji, _col, _tip in _CONF_EMOJIS:
                                        ui.button(_emoji).props("flat round dense").classes(
                                            f"text-lg text-{_col}-500 hover:bg-{_col}-50 dark:hover:bg-slate-700"
                                        ).on_click(
                                            _make_quick_val(_score, task, card, _val_menu, _base_dur)
                                        ).tooltip(f"{_tip} ({_score}/5)")

                            ui.separator().classes("mb-1")
                            ui.menu_item(
                                "Détailler...",
                                on_click=lambda t=task, c=card: open_session_feedback_dialog(
                                    t, c, validate_fn
                                ),
                            ).classes("text-xs text-slate-500 font-medium")
                            ui.separator()
                            ui.menu_item(
                                "Lacune...",
                                on_click=lambda t=task, r=on_lacune_saved: open_lacune_inline_dialog(t, on_save=r),
                            ).classes("text-xs text-amber-600 font-medium")
```

Replace with:

```python
                    ui.button("⏱").props("flat round dense size=xs").classes(
                        "text-slate-300 hover:text-orange-500 shrink-0"
                    ).tooltip("Chronométrer (pré-remplit la durée du dialog)").on_click(_toggle_timer)

                    # Bouton Valider — ouvre toujours le dialog complet.
                    # Si le chrono tournait, sa durée pré-remplit le dialog.
                    def _make_open_dialog(t, c, _ts=_tstate):
                        def _h():
                            _dur = None
                            if _ts["t0"] is not None:
                                _dur = max(1, int(
                                    (datetime.datetime.now() - _ts["t0"]).total_seconds() / 60
                                ))
                            open_session_feedback_dialog(t, c, validate_fn, initial_duration_minutes=_dur)
                        return _h

                    ui.button("Valider").props(
                        "unelevated rounded dense size=sm color=cyan"
                        " aria-label='Valider la révision'"
                    ).classes("text-[11px] font-bold px-3").on_click(
                        _make_open_dialog(task, card)
                    ).tooltip("Valider (détails)")

                    if on_postpone:
                        def _make_pass(t=task, c=card):
                            async def _h():
                                await on_postpone(t, c, 7)
                            return _h

                        ui.button("Passer").props(
                            "flat rounded dense size=sm color=slate"
                        ).classes("text-[11px] font-semibold px-2").on_click(
                            _make_pass()
                        ).tooltip("Passer (7 jours)")

                    with ui.button(icon="tune").props(
                        "flat round dense size=sm color=green aria-label='Options'"
                    ).tooltip("Confiance rapide, report fin, lacune…"):
                        with ui.menu() as _val_menu:
                            _CONF_EMOJIS = [
                                (1, "😰", "red",   "Très difficile"),
                                (2, "😟", "orange","Difficile"),
                                (3, "😐", "blue",  "Moyen"),
                                (4, "😊", "teal",  "Facile"),
                                (5, "🔥", "green", "Parfait !"),
                            ]
                            _TYPE_DUR_BASE = {
                                "J3": 15, "J7": 20, "J14": 25, "J30": 30,
                                "bonus": 30, "qcm_error": 20, "manuel": 20,
                            }
                            _base_dur = _TYPE_DUR_BASE.get(task.review_type, 20)

                            def _make_quick_val(score, t, c, menu, base):
                                _score_map = {
                                    1: (max(base, 30), "difficile"),
                                    2: (max(base, 25), "difficile"),
                                    3: (base,          "moyen"),
                                    4: (min(base, 15), "facile"),
                                    5: (10,            "facile"),
                                }
                                _dur, _diff = _score_map[score]
                                async def _h():
                                    menu.close()
                                    await on_done(t, c, ["révision"], _dur, score, _diff)
                                return _h

                            with ui.element("div").classes("px-3 pt-3 pb-2 flex flex-col gap-2"):
                                ui.label("Confiance ?").classes(
                                    "text-[11px] font-bold text-slate-400 uppercase tracking-wide"
                                )
                                with ui.row().classes("gap-1 justify-center mt-1"):
                                    for _score, _emoji, _col, _tip in _CONF_EMOJIS:
                                        ui.button(_emoji).props("flat round dense").classes(
                                            f"text-lg text-{_col}-500 hover:bg-{_col}-50 dark:hover:bg-slate-700"
                                        ).on_click(
                                            _make_quick_val(_score, task, card, _val_menu, _base_dur)
                                        ).tooltip(f"{_tip} ({_score}/5)")

                            ui.separator().classes("mb-1")
                            ui.menu_item(
                                "Lacune...",
                                on_click=lambda t=task, r=on_lacune_saved: open_lacune_inline_dialog(t, on_save=r),
                            ).classes("text-xs text-amber-600 font-medium")

                            if on_postpone or on_ignore:
                                ui.separator()
                                if on_postpone:
                                    def _wrap_post(d, t=task, c=card, m=_val_menu):
                                        async def _h():
                                            m.close()
                                            await on_postpone(t, c, d)
                                        return _h
                                    ui.menu_item("+1 jour",    on_click=_wrap_post(1)).classes("text-xs")
                                    ui.menu_item("+3 jours",   on_click=_wrap_post(3)).classes("text-xs")
                                    ui.menu_item("+1 semaine", on_click=_wrap_post(7)).classes(
                                        "text-xs text-amber-600"
                                    ).tooltip("Peut créer un retard critique")
                                if on_ignore:
                                    ui.separator()
                                    def _wrap_ign(t=task, c=card, m=_val_menu):
                                        async def _h():
                                            m.close()
                                            await on_ignore(t, c)
                                        return _h
                                    ui.menu_item("Ignorer", on_click=_wrap_ign()).classes("text-xs text-red-400")
```

- [ ] **Step 2: Remove the now-redundant standalone postpone/ignore icons**

A few lines below in the same function, remove this whole block (the fine-grained postpone options and the Ignorer close-icon are now inside the "⋯" menu from Step 1):

```python
                    # ── Reporter (menu déroulant) + Ignorer ───────────────────
                    if on_postpone or on_ignore:
                        def wrap_post(t, c, d):
                            async def _h(): await on_postpone(t, c, d)
                            return _h
                        def wrap_ign(t, c):
                            async def _h(): await on_ignore(t, c)
                            return _h

                        with ui.element("div"):
                            _postpone_btn = ui.button(icon="skip_next").props(
                                "flat round dense size=xs color=grey-7"
                            ).tooltip("Reporter")
                            with ui.menu() as _postpone_menu:
                                _postpone_btn.on("click", _postpone_menu.open)
                                ui.menu_item(
                                    "+1 jour",
                                    on_click=wrap_post(task, card, 1),
                                ).classes("text-xs")
                                ui.menu_item(
                                    "+3 jours",
                                    on_click=wrap_post(task, card, 3),
                                ).classes("text-xs")
                                ui.menu_item(
                                    "+1 semaine",
                                    on_click=wrap_post(task, card, 7),
                                ).classes("text-xs text-amber-600").tooltip(
                                    "Peut créer un retard critique"
                                )

                        ui.button(icon="close").props(
                            "flat round dense size=xs color=grey-7"
                        ).classes(
                            "opacity-50 hover:opacity-100 transition-opacity"
                        ).tooltip("Ignorer cette révision").on_click(
                            wrap_ign(task, card)
                        )
```

Delete it entirely (do not leave an empty `if` block behind).

- [ ] **Step 3: Manual verification**

Restart the app. Open Mode Focus (focus icon on the Dashboard toolbar) with at least one item queued:
- Start the ⏱ chrono, wait ~1 minute, click "Valider" → the dialog opens with duration pre-filled to the elapsed minutes (shown either as a highlighted preset or in the small custom-duration field).
- Click "Passer" → item is postponed 7 days and Focus mode advances to the next item.
- Open the "⋯" (tune) menu → confidence emojis, a separator, "Lacune...", a separator, "+1 jour"/"+3 jours"/"+1 semaine", a separator, "Ignorer" — no standalone skip_next/close icons remain in the action row.

- [ ] **Step 4: Commit**

```bash
git add frontend/pages/dashboard/_reviews.py
git commit -m "feat(dashboard): unify Focus-mode Valider button and fold postpone/ignore into the options menu"
```

---

### Task 6: planning.py — reuse `render_review_row`, drop `_consolidation_card`

**Files:**
- Modify: `frontend/pages/planning.py:1-32` (imports)
- Modify: `frontend/pages/planning.py:125-161` (delete `_consolidation_card`)
- Modify: `frontend/pages/planning.py:526-630` (consolidation callbacks + render loop)

**Interfaces:**
- Consumes: `render_review_row` from `frontend.pages.dashboard._reviews`; `complete_consolidation_task` from `backend.core.reviews.consolidation` (Task 1).
- Produces: no new public interface — this task only changes how the Consolidation tab renders internally.

- [ ] **Step 1: Update imports**

At the top of `frontend/pages/planning.py`, change:

```python
from __future__ import annotations

import datetime
from nicegui import ui

from frontend.theme import frame
from backend.core.planning.models import PlannedSlot, DailyPlan
from backend.core.planning.service import planning_service
from backend.core.reviews.service import review_service
from backend.core.reviews.local_store import (
    get_all_history, get_sessions_by_course, get_postpone_counts,
    get_all_weak_points_table,
)
from backend.core.google.calendar_service import calendar_service
from backend.core.reviews import consolidation
from backend.core.reviews.local_store import mark_consolidation_done, postpone as postpone_task, add_study_session
from backend.core.reviews.models import ReviewTask
from frontend.pages.dashboard._dialogs import open_session_feedback_dialog
from backend.state.store import data_store
```

to:

```python
from __future__ import annotations

import asyncio
import datetime
from nicegui import ui

from frontend.theme import frame
from backend.core.planning.models import PlannedSlot, DailyPlan
from backend.core.planning.service import planning_service
from backend.core.reviews.service import review_service
from backend.core.reviews.local_store import (
    get_all_history, get_sessions_by_course, get_postpone_counts,
    get_all_weak_points_table,
)
from backend.core.google.calendar_service import calendar_service
from backend.core.reviews import consolidation
from backend.core.reviews.local_store import postpone as postpone_task
from backend.core.reviews.models import ReviewTask
from frontend.pages.dashboard._dialogs import open_session_feedback_dialog
from frontend.pages.dashboard._reviews import render_review_row
from backend.state.store import data_store
```

(`mark_consolidation_done` and `add_study_session` are no longer called directly from this file — `consolidation.complete_consolidation_task` replaces both call sites. `asyncio` is newly needed for the lacune-save refresh callback in Step 3.)

- [ ] **Step 2: Delete `_consolidation_card`**

Remove this entire function from `frontend/pages/planning.py`:

```python
# ── Composant ConsolidationCard ────────────────────────────────────────────

def _consolidation_card(task: ReviewTask, on_validate, on_postpone):
    """Carte d'un item du flux de consolidation, avec actions Valider/Passer."""
    with ui.card().classes(
        "w-full p-0 rounded-xl border-l-4 border-l-cyan-500 "
        "border-y border-r border-slate-100 dark:border-slate-800 "
        "shadow-sm hover:shadow-md transition-all overflow-hidden"
    ) as card:
        with ui.row().classes("items-center gap-3 px-3 py-2.5 w-full"):
            ui.icon("history_edu", size="sm").classes("text-cyan-500 shrink-0")

            with ui.column().classes("flex-1 gap-0 min-w-0"):
                ui.label(task.label).classes(
                    "text-sm font-semibold text-slate-800 dark:text-slate-100 leading-snug"
                ).style(
                    "overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
                ).tooltip(task.label)
                sub_parts = []
                if task.college:
                    sub_parts.append(", ".join(task.college[:2]))
                if task.mastery_level:
                    sub_parts.append(f"niveau {task.mastery_level}")
                if task.days_overdue > 0:
                    sub_parts.append(f"{task.days_overdue}j de retard")
                ui.label(" · ".join(sub_parts) or "à consolider").classes(
                    "text-[11px] text-slate-500 dark:text-slate-400"
                )

            with ui.row().classes("items-center gap-1 shrink-0"):
                ui.button("Passer", on_click=lambda: on_postpone(task)).props(
                    "flat dense size=sm color=slate"
                )
                ui.button("Valider", icon="check", on_click=lambda t=task, c=card: on_validate(t, c)).props(
                    "unelevated dense size=sm color=cyan"
                )
    return card
```

(The blank line(s) around it collapse to a single blank line separating the preceding and following functions — match the file's existing spacing convention.)

- [ ] **Step 3: Rewire the consolidation render block**

Inside `_planifier()`, the `if mode_state["value"] == "consolidation":` branch currently defines `_do_mark_consolidation`, `_on_validate`, `_on_postpone`, `_search_courses`, `_add_course_worked`, `_render_consolidation`. Replace the whole branch body with:

```python
                if mode_state["value"] == "consolidation":
                    async def _refresh_consolidation():
                        selected, _skipped = planning_service.plan_consolidation()
                        plan_container.clear()
                        with plan_container:
                            _render_consolidation(selected)

                    async def _do_mark_consolidation(
                        t: ReviewTask, card,
                        activity_types=None, duration_minutes=None,
                        confidence=None, difficulty=None, qcm_result=None,
                        weak_category=None, weak_detail=None,
                    ) -> None:
                        consolidation.complete_consolidation_task(
                            t,
                            activity_types=activity_types, duration_minutes=duration_minutes,
                            confidence=confidence, difficulty=difficulty, qcm_result=qcm_result,
                            weak_category=weak_category, weak_detail=weak_detail,
                        )
                        ui.notify(f"✓ Consolidé : {t.course_title}", type="positive")
                        await _refresh_consolidation()

                    async def _on_postpone(t: ReviewTask, card, days: int = 7) -> None:
                        postpone_task(
                            task_id=t.id, course_id=t.course_id, context=t.context,
                            review_type="consolidation",
                            theoretical_due_date=t.theoretical_due_date,
                            postponed_to=datetime.date.today() + datetime.timedelta(days=days),
                            course_title=t.course_title, item_number=t.item_number or "",
                        )
                        ui.notify(f"Reporté : {t.course_title}", type="info")
                        await _refresh_consolidation()

                    def _on_lacune_saved() -> None:
                        asyncio.create_task(_refresh_consolidation())

                    def _search_courses(query: str) -> list:
                        q = query.strip()
                        if len(q) < 2:
                            return []
                        try:
                            from backend.core.search.service import search_index
                            hits = search_index.search(q, limit=8, score_cutoff=50)
                            return [c for c, _ in hits]
                        except Exception:
                            q_low = q.lower()
                            return [
                                c for c in data_store.cours
                                if q_low in c.title.lower()
                                or (c.item_number and q_low in c.item_number)
                            ][:8]

                    async def _add_course_worked(course_id: str) -> None:
                        task = consolidation.get_or_bootstrap_task(course_id, context="college")
                        if task is None:
                            ui.notify("Cours introuvable ou jamais commencé.", type="warning")
                            return
                        dummy_card = ui.card()  # cible d'animation pour le dialogue existant
                        dummy_card.set_visibility(False)
                        open_session_feedback_dialog(task, dummy_card, _do_mark_consolidation)

                    def _render_consolidation(tasks: list[ReviewTask]) -> None:
                        with ui.row().classes("items-center gap-2 w-full mb-3"):
                            search_input = ui.input(
                                placeholder="Ajouter un cours travaillé aujourd'hui…"
                            ).props("outlined dense clearable").classes("flex-1")
                            results_container = ui.column().classes("w-full gap-1")

                            def _on_search(e):
                                results_container.clear()
                                hits = _search_courses(e.value or "")
                                with results_container:
                                    for c in hits:
                                        label = f"ITEM {c.item_number} – {c.title}" if c.item_number else c.title
                                        ui.button(
                                            label,
                                            on_click=lambda cid=c.id: _add_course_worked(cid),
                                        ).props("flat dense align=left size=sm color=slate").classes(
                                            "w-full justify-start normal-case"
                                        )

                            search_input.on("update:model-value", _on_search)

                        if not tasks:
                            with ui.column().classes("w-full items-center py-8 gap-2 text-slate-400"):
                                ui.icon("check_circle_outline", size="xl").classes("text-green-400")
                                ui.label("Rien à consolider aujourd'hui.").classes("text-sm")
                            return

                        with ui.row().classes("items-center justify-between w-full mb-2"):
                            ui.label(f"{len(tasks)} item(s) à consolider").classes(
                                "text-xs font-bold text-cyan-600 uppercase tracking-wider"
                            )

                            async def _postpone_all():
                                for t in list(tasks):
                                    await _on_postpone(t, None)

                            ui.button("Tout reporter", icon="skip_next", on_click=_postpone_all).props(
                                "flat dense size=sm color=slate"
                            )

                        for t in tasks:
                            render_review_row(
                                plan_container, t,
                                on_done=_do_mark_consolidation,
                                on_postpone=_on_postpone,
                                on_ignore=None,
                                validate_fn=_do_mark_consolidation,
                                on_lacune_saved=_on_lacune_saved,
                                is_overdue=t.days_overdue > 0,
                            )

                    await _refresh_consolidation()
```

What changed vs. the original:
- `_do_mark_consolidation` now delegates to `consolidation.complete_consolidation_task` (Task 1) instead of calling `mark_consolidation_done` + `add_study_session` itself.
- `_on_postpone` gains a `card` parameter (ignored — no exit animation in this context) to match `render_review_row`'s 3-arg call convention; `_postpone_all` passes `None` for it.
- `_on_validate` is deleted — it only ever wrapped `open_session_feedback_dialog(t, card, _do_mark_consolidation)`, which `render_review_row` now does internally via its `validate_fn` parameter.
- New `_on_lacune_saved` sync wrapper bridges `render_review_row`'s sync `on_lacune_saved` callback to the async `_refresh_consolidation`.
- The render loop calls `render_review_row(plan_container, t, ...)` instead of `_consolidation_card(t, _on_validate, _on_postpone)`. `qcm_info`/`lacune_count` are intentionally left at their defaults (`None`/`0`) — planning.py never fetched per-course QCM scores or lacune counts before, and adding that batch lookup here is out of scope for this unification (see the design doc's "Hors scope" note if this needs revisiting later).

- [ ] **Step 4: Manual verification**

Restart the app. Go to Planning → Consolidation tab:
- Confirm the list renders with the new row layout: `[✓ Valider] [⏭ Passer] [⋯]`, college label, PDF/Fiche EDN icons where applicable.
- Click ✓ → dialog opens, submitting it advances the SM-2 chain and shows "✓ Consolidé : …".
- Click ⏭ → item is postponed 7 days, disappears from today's list, notification "Reporté : …" appears.
- Open "⋯" → confidence emojis, Lacune…, +1 jour/+3 jours/+1 semaine, all work and refresh the list.
- Add a lacune via "⋯" → "Lacune…" dialog saves, and the consolidation list refreshes (via `_on_lacune_saved`) without a full page reload.
- "Tout reporter" still postpones every item in the list.
- Use the search box to add a course "travaillé aujourd'hui" → still opens the dialog via `_add_course_worked` as before.

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/planning.py
git commit -m "refactor(planning): reuse render_review_row for consolidation tab, drop duplicate _consolidation_card"
```

---

### Task 7: Full regression pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend test suite**

Run: `"/c/Users/hugol/AppData/Local/Programs/Python/Python313/python.exe" -m pytest -q`
Expected: same pass/fail baseline as before this plan (this repo has 4 known pre-existing failures in `test_lisa_scraper.py`, unrelated to this work — confirm no *new* failures appeared).

- [ ] **Step 2: Full manual walkthrough**

Restart the app fresh (`Ctrl+C` then `python main.py`) and, in one sitting, exercise all three surfaces end to end:
1. Dashboard RETARD/AUJOURD'HUI: validate one item of each kind reachable today (a J-cycle item, a consolidation item if any is due) — dialog opens both times, Passer works both times.
2. Mode Focus: open it, validate one item using the chrono-prefill path, postpone one, check the "⋯" menu options all work, confirm it advances to the next item / closes with the "Focus terminé" toast when the queue empties.
3. Planning → Consolidation: validate one, postpone one, add a lacune, add a manually-searched course.

- [ ] **Step 3: Final commit (if any fixups were needed during the walkthrough)**

```bash
git add -A
git commit -m "fix: address issues found during session-validation unification regression pass"
```

(Skip this step entirely if the walkthrough found nothing to fix.)
