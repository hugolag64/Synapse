# Plafond de charge quotidienne — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user cap how many minutes of review work (urgent + today + consolidation combined) the dashboard proposes per day, instead of the current unbounded "Voir plus" reveal.

**Architecture:** A new preference `daily_budget_min` (minutes, 0 = unlimited) drives a pure trimming function `apply_daily_budget()` in `recommendation_service.py` that truncates the already priority-sorted `urgent`/`today_tasks` lists in `rebuild_all()` before rendering. Cut items are never mutated — their `due_date` is untouched, so they reappear naturally next day (same rollover mechanism `consolidation.select_daily` already relies on). `compute_daily_load()` gains an optional threshold param so the "charge lourde" signal can be computed against the user's own budget instead of a hardcoded 120 min. The active dashboard banner gets a new pill to surface both "heavy load" and "N items reportées" — neither currently exists there (only the legacy dashboard has a heavy badge, on `is_heavy` computed against a fixed 120).

**Tech Stack:** Python, pydantic (`ReviewTask` model), pytest, NiceGUI (UI wiring only, unit-tested indirectly through pure functions).

## Global Constraints

- Spec source of truth: `docs/superpowers/specs/2026-07-20-daily-workload-budget-design.md`.
- Unit: **minutes** (`get_next_action(t).duration_min`), not item count.
- Scope: **unified budget** across `urgent_tasks` + `today_tasks` (no exemption for overdue items).
- Default: `daily_budget_min` defaults to `0` (unlimited) everywhere it's read — behavior must not change until the user sets a value in Settings.
- No new persisted state for "skipped" items — cut items keep their original `due_date` and roll over implicitly.
- `apply_daily_budget` must NOT re-sort its inputs — `urgent_tasks`/`today_tasks` already arrive priority-sorted from `ReviewService.generate_reviews` (`backend/core/reviews/service.py:212,263`).

---

### Task 1: `apply_daily_budget()` in `recommendation_service.py`

**Files:**
- Modify: `backend/core/reviews/recommendation_service.py`
- Test: `tests/test_recommendation_service.py` (new file)

**Interfaces:**
- Consumes: `ReviewTask` (from `backend.core.reviews.models`), `get_next_action` (already defined in this same file, `recommendation_service.py:45`).
- Produces: `apply_daily_budget(urgent_tasks: list[ReviewTask], today_tasks: list[ReviewTask], budget_min: int) -> tuple[list[ReviewTask], list[ReviewTask], int]` — the third element is `overflow_count` (number of tasks cut). Task 4 imports this exact name and signature.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_recommendation_service.py`:

```python
"""Tests unitaires — recommendation_service (charge journalière + plafond)."""
import datetime
from backend.core.reviews.models import ReviewTask


def _task(course_id, review_type="J7", days_overdue=0, due_date=None):
    due = due_date or datetime.date.today()
    return ReviewTask(
        id=f"{course_id}_{review_type}",
        course_id=course_id,
        course_title=course_id,
        theoretical_due_date=due,
        due_date=due,
        review_type=review_type,
        days_overdue=days_overdue,
    )


# ── apply_daily_budget ───────────────────────────────────────────────────────

def test_apply_daily_budget_no_op_quand_budget_zero():
    from backend.core.reviews.recommendation_service import apply_daily_budget

    urgent = [_task("u1", days_overdue=1)]
    today = [_task("t1"), _task("t2")]
    kept_u, kept_t, overflow = apply_daily_budget(urgent, today, budget_min=0)

    assert kept_u == urgent
    assert kept_t == today
    assert overflow == 0


def test_apply_daily_budget_liste_vide():
    from backend.core.reviews.recommendation_service import apply_daily_budget

    kept_u, kept_t, overflow = apply_daily_budget([], [], budget_min=60)
    assert kept_u == []
    assert kept_t == []
    assert overflow == 0


def test_apply_daily_budget_budget_suffisant_pour_tout():
    from backend.core.reviews.recommendation_service import apply_daily_budget

    # 1 urgent (20 min, cf. get_next_action: overdue>0 non-critique) +
    # 1 today (30 min, cf. get_next_action: pas de QCM fait)
    urgent = [_task("u1", days_overdue=1)]
    today = [_task("t1")]
    kept_u, kept_t, overflow = apply_daily_budget(urgent, today, budget_min=100)

    assert kept_u == urgent
    assert kept_t == today
    assert overflow == 0


def test_apply_daily_budget_coupe_dans_today_tasks():
    from backend.core.reviews.recommendation_service import apply_daily_budget

    # 1 urgent = 20 min. 3 today = 30 min chacune.
    # Budget 50 -> urgent (20) + 1 today (30) = 50, le reste des today est coupé.
    urgent = [_task("u1", days_overdue=1)]
    today = [_task("t1"), _task("t2"), _task("t3")]
    kept_u, kept_t, overflow = apply_daily_budget(urgent, today, budget_min=50)

    assert [t.course_id for t in kept_u] == ["u1"]
    assert [t.course_id for t in kept_t] == ["t1"]
    assert overflow == 2


def test_apply_daily_budget_coupe_dans_urgent_tasks():
    from backend.core.reviews.recommendation_service import apply_daily_budget

    # 3 urgent = 20 min chacune. Budget 30 -> seule la 1ère urgent (20 min) tient,
    # aucune today n'est retenue.
    urgent = [_task("u1", days_overdue=1), _task("u2", days_overdue=2), _task("u3", days_overdue=3)]
    today = [_task("t1")]
    kept_u, kept_t, overflow = apply_daily_budget(urgent, today, budget_min=30)

    assert [t.course_id for t in kept_u] == ["u1"]
    assert kept_t == []
    assert overflow == 3  # 2 urgent + 1 today


def test_apply_daily_budget_conserve_lordre_recu_sans_retrier():
    from backend.core.reviews.recommendation_service import apply_daily_budget

    # today_tasks volontairement dans un ordre non trié par priority_score :
    # apply_daily_budget ne doit PAS le retrier, juste couper à la fin.
    today = [_task("low_prio"), _task("high_prio")]
    kept_u, kept_t, overflow = apply_daily_budget([], today, budget_min=30)

    assert [t.course_id for t in kept_t] == ["low_prio"]
    assert overflow == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_recommendation_service.py -v`
Expected: FAIL — `ImportError: cannot import name 'apply_daily_budget'`

- [ ] **Step 3: Implement `apply_daily_budget`**

In `backend/core/reviews/recommendation_service.py`, add after `compute_daily_load` (end of file, after line 227):

```python
def apply_daily_budget(
    urgent_tasks: list["ReviewTask"],
    today_tasks:  list["ReviewTask"],
    budget_min: int,
) -> tuple[list["ReviewTask"], list["ReviewTask"], int]:
    """
    Tronque urgent_tasks + today_tasks (dans cet ordre, sans les retrier —
    ils arrivent déjà triés par priority_score décroissant depuis
    ReviewService.generate_reviews) pour que le total estimé ne dépasse pas
    budget_min minutes. budget_min <= 0 désactive le plafond (no-op).

    Ne modifie aucune due_date : les items coupés repasseront naturellement
    le(s) jour(s) suivant(s) (même logique que consolidation.select_daily).

    Retourne (kept_urgent, kept_today, overflow_count).
    """
    if budget_min <= 0:
        return urgent_tasks, today_tasks, 0

    kept_urgent: list["ReviewTask"] = []
    kept_today: list["ReviewTask"] = []
    total_min = 0
    overflow = 0

    for bucket_in, bucket_out in ((urgent_tasks, kept_urgent), (today_tasks, kept_today)):
        for t in bucket_in:
            duration = get_next_action(t).duration_min
            if total_min + duration > budget_min:
                overflow += 1
                continue
            bucket_out.append(t)
            total_min += duration

    return kept_urgent, kept_today, overflow
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_recommendation_service.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/core/reviews/recommendation_service.py tests/test_recommendation_service.py
git commit -m "$(cat <<'EOF'
feat(reviews): add apply_daily_budget to cap daily review workload

Pure trimming function over already-sorted urgent/today lists, cut by
cumulative estimated minutes. Cut items keep their due_date so they
roll over to the next day automatically.
EOF
)"
```

---

### Task 2: `compute_daily_load` — configurable heavy threshold

**Files:**
- Modify: `backend/core/reviews/recommendation_service.py`
- Test: `tests/test_recommendation_service.py`

**Interfaces:**
- Consumes: existing `compute_daily_load(urgent_tasks, today_tasks)` (recommendation_service.py:199-227).
- Produces: `compute_daily_load(urgent_tasks, today_tasks, heavy_threshold_min: int = 120) -> dict` — same return shape as before (`total_min`, `urgent_count`, `today_count`, `is_heavy`, `estimated_h`, `estimated_m`). Task 4/5 pass `heavy_threshold_min` explicitly.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_recommendation_service.py`:

```python
# ── compute_daily_load : seuil configurable ─────────────────────────────────

def test_compute_daily_load_seuil_par_defaut_120():
    from backend.core.reviews.recommendation_service import compute_daily_load

    # 5 today tasks * 30 min = 150 min > 120
    today = [_task(f"t{i}") for i in range(5)]
    load = compute_daily_load([], today)
    assert load["total_min"] == 150
    assert load["is_heavy"] is True


def test_compute_daily_load_seuil_personnalise():
    from backend.core.reviews.recommendation_service import compute_daily_load

    # 3 today tasks * 30 min = 90 min : pas heavy avec seuil par défaut 120,
    # mais heavy avec un seuil personnalisé à 60.
    today = [_task(f"t{i}") for i in range(3)]
    load_default = compute_daily_load([], today)
    assert load_default["is_heavy"] is False

    load_custom = compute_daily_load([], today, heavy_threshold_min=60)
    assert load_custom["is_heavy"] is True
    assert load_custom["total_min"] == 90  # total_min ne dépend pas du seuil
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_recommendation_service.py -v`
Expected: FAIL — `TypeError: compute_daily_load() got an unexpected keyword argument 'heavy_threshold_min'`

- [ ] **Step 3: Update `compute_daily_load`**

In `backend/core/reviews/recommendation_service.py`, replace the existing function (lines 199-227):

```python
def compute_daily_load(
    urgent_tasks: list["ReviewTask"],
    today_tasks:  list["ReviewTask"],
    heavy_threshold_min: int = 120,
) -> dict:
    """
    Estime la charge journalière (urgent + prévu aujourd'hui).

    Retourne :
        {
            "total_min"     : int,    # total estimé en minutes
            "urgent_count"  : int,
            "today_count"   : int,
            "is_heavy"      : bool,   # True si > heavy_threshold_min
            "estimated_h"   : int,    # heures entières
            "estimated_m"   : int,    # minutes restantes
        }
    """
    all_tasks = urgent_tasks + today_tasks
    total_min = sum(get_next_action(t).duration_min for t in all_tasks)
    h, m = divmod(total_min, 60)

    return {
        "total_min"   : total_min,
        "urgent_count": len(urgent_tasks),
        "today_count" : len(today_tasks),
        "is_heavy"    : total_min > heavy_threshold_min,
        "estimated_h" : h,
        "estimated_m" : m,
    }
```

The module docstring example at the top of the file (lines 13-14, `load = compute_daily_load(urgent_tasks, today_tasks)`) stays valid as-is since `heavy_threshold_min` defaults to `120` — no docstring edit needed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_recommendation_service.py -v`
Expected: PASS (8 tests total)

- [ ] **Step 5: Run the full existing test suite to check for regressions**

Run: `python -m pytest tests/ -v -k "not lisa_scraper"`
Expected: PASS (same baseline as before this change — pre-existing `test_lisa_scraper.py` failures are unrelated, cf. `docs/superpowers/specs/2026-07-19-*` history).

- [ ] **Step 6: Commit**

```bash
git add backend/core/reviews/recommendation_service.py tests/test_recommendation_service.py
git commit -m "$(cat <<'EOF'
feat(reviews): make compute_daily_load's heavy threshold configurable

Defaults to 120 min (unchanged behavior). Callers can now pass the
user's own daily_budget_min so the "heavy load" signal matches their
personal cap instead of a hardcoded value.
EOF
)"
```

---

### Task 3: Settings UI — `daily_budget_min` preference

**Files:**
- Modify: `frontend/pages/settings.py:242-261` (the "Objectif quotidien" card)

**Interfaces:**
- Consumes: `data_store.preferences.get(...)`, `data_store.set_preference(...)` (existing pattern, e.g. `settings.py:252,257` for `daily_goal`).
- Produces: preference key `"daily_budget_min"` (int, minutes, default `0`) that Task 4 reads via `data_store.preferences.get("daily_budget_min", 0)`.

- [ ] **Step 1: Add the field**

In `frontend/pages/settings.py`, inside the existing "Objectif quotidien" card (right after the `_goal_inp.on('blur', _save_goal)` line, currently line 261), add a second row in the same card:

```python
            with ui.row().classes('w-full items-center gap-4 mt-2'):
                ui.icon('speed', color='amber').classes('text-xl shrink-0')
                with ui.column().classes('gap-0 flex-1'):
                    ui.label('Charge max quotidienne').classes('font-semibold text-sm text-slate-700 dark:text-slate-200')
                    ui.label('0 = illimité — plafonne retard + aujourd\'hui + consolidation').classes('text-xs text-slate-400 dark:text-slate-500')
                _budget_inp = ui.number(
                    value=data_store.preferences.get('daily_budget_min', 0), min=0, max=300, step=15,
                ).props('outlined dense').classes('w-28')
                ui.label('min / jour').classes('text-xs text-slate-500 shrink-0')
            def _save_budget(e):
                try:
                    data_store.set_preference('daily_budget_min', int(e.value))
                    ui.notify(f"Charge max : {int(e.value)} min/jour ✓" if int(e.value) > 0 else "Charge max désactivée", type='positive', timeout=1500)
                except Exception:
                    pass
            _budget_inp.on('blur', _save_budget)
```

This mirrors the existing `daily_goal` field exactly (same card, same `ui.number` + `.on('blur', ...)` pattern), so it inherits the same styling and persistence behavior (`data_store.set_preference` already handles saving to disk — verify by reading `backend/state/store.py::set_preference` if unsure, but `daily_goal` above uses the identical call with no extra save step).

- [ ] **Step 2: Verify no syntax/import errors**

Run: `python -c "import ast; ast.parse(open('frontend/pages/settings.py', encoding='utf-8').read())"`
Expected: no output (parses cleanly)

Run: `python -c "from frontend.pages import settings"`
Expected: no output / no exception (confirms imports resolve, since NiceGUI page functions aren't executed at import time)

- [ ] **Step 3: Manual verification**

Start the app per the project's usual run method (`run` skill or existing dev script), open `/settings`, confirm:
- The new "Charge max quotidienne" field appears under "Objectif quotidien", defaulting to `0`.
- Changing the value and blurring the field shows the notify toast and persists (reload the page, value should stick).

- [ ] **Step 4: Commit**

```bash
git add frontend/pages/settings.py
git commit -m "feat(settings): add daily_budget_min field to cap daily review workload"
```

---

### Task 4: Wire the budget trim into `rebuild_all()`

**Files:**
- Modify: `frontend/pages/dashboard/_reviews.py`

**Interfaces:**
- Consumes: `apply_daily_budget` and `compute_daily_load` (Task 1/2, `backend.core.reviews.recommendation_service`), `data_store` (`backend.state.store`), `update_banner` (Task 5 changes its signature — this task passes the new `overflow_count` argument).
- Produces: `rebuild_all()` behavior — `state.urgent_col`/`state.today_col` render at most `daily_budget_min` worth of minutes when the preference is set.

- [ ] **Step 1: Add the `data_store` import**

In `frontend/pages/dashboard/_reviews.py`, add to the import block (after line 18, `from backend.core.externat.service import externat_service`):

```python
from backend.state.store import data_store
```

- [ ] **Step 2: Update the `compute_daily_load` import and call**

Find (around line 888):

```python
    from backend.core.reviews.recommendation_service import compute_daily_load
    load = compute_daily_load(urgent, today_tasks)
    update_banner(state, load, done_today=state.done_today_count, week_count=_week_count)
```

Replace with:

```python
    from backend.core.reviews.recommendation_service import compute_daily_load, apply_daily_budget
    _daily_budget = data_store.preferences.get("daily_budget_min", 0)
    load = compute_daily_load(
        urgent, today_tasks,
        heavy_threshold_min=_daily_budget if _daily_budget > 0 else 120,
    )
    urgent, today_tasks, _overflow_count = apply_daily_budget(urgent, today_tasks, _daily_budget)
    update_banner(state, load, done_today=state.done_today_count, week_count=_week_count, overflow_count=_overflow_count)
```

This must run **after** `state.focus_tasks = urgent + today_tasks` (line 878, unchanged — Mode Focus keeps seeing the untrimmed set, consistent with "voir plus" no longer being the only bound) and **before** the RETARD/AUJOURD'HUI rendering sections (`state.urgent_col.clear()` at line 921 and `state.today_col.clear()` at line 941), which already operate on `urgent`/`today_tasks` by name — no further changes needed there since the trim reassigns those same local variables in place.

- [ ] **Step 3: Verify no syntax/import errors**

Run: `python -c "import ast; ast.parse(open('frontend/pages/dashboard/_reviews.py', encoding='utf-8').read())"`
Expected: no output

Run: `python -c "from frontend.pages.dashboard import _reviews"`
Expected: no output / no exception

- [ ] **Step 4: Run the full test suite**

Run: `python -m pytest tests/ -v -k "not lisa_scraper"`
Expected: PASS, no regressions (this file has no direct unit tests, but confirms nothing else broke by importing it — e.g. `test_consolidation.py`'s `complete_consolidation_task` path).

- [ ] **Step 5: Commit**

(Bundled with Task 5's `update_banner` signature change since both must land together to keep the app importable — see Task 5 Step 3 for the combined commit.)

---

### Task 5: Banner — heavy-load pill + overflow message

**Files:**
- Modify: `frontend/pages/dashboard/_banner.py`

**Interfaces:**
- Consumes: `state.banner_refs` (dict, `_state.py:24`), `load["is_heavy"]` (Task 2).
- Produces: `update_banner(state, load, done_today=0, week_count=0, overflow_count=0)` — new keyword-only-by-convention parameter `overflow_count` (positional-or-keyword, default `0`, so existing call sites without it keep working). Task 4 already calls it with `overflow_count=_overflow_count`.

- [ ] **Step 1: Add the "heavy" pill markup to `render_banner`**

In `frontend/pages/dashboard/_banner.py`, after the "Objectif quotidien" pill block (after line 66, `state.banner_refs["goal_el"].set_visibility(False)`), add:

```python
                # Charge lourde / plafond atteint
                state.banner_refs["heavy_el"] = ui.element("div").classes(
                    "flex items-center gap-1.5 px-2.5 py-1 rounded-full "
                    "bg-amber-50 dark:bg-amber-900/20 cursor-pointer"
                ).on("click", lambda: ui.navigate.to("/settings"))
                with state.banner_refs["heavy_el"]:
                    ui.icon("warning", size="xs").classes("text-amber-500")
                    state.banner_refs["heavy"] = ui.label("").classes(
                        "text-[12px] font-semibold text-amber-700 dark:text-amber-400"
                    )
                state.banner_refs["heavy_el"].set_visibility(False)
```

- [ ] **Step 2: Update `update_banner` to populate it**

Change the function signature (line 96):

```python
def update_banner(state: DashboardState, load: dict, done_today: int = 0, week_count: int = 0, overflow_count: int = 0) -> None:
```

At the end of the function body (after the existing "Objectif quotidien + barre de progression" block, i.e. after line 154's `state.banner_refs["daily_bar"].set_visibility(False)` and its enclosing `if/else`), add:

```python
    # Charge lourde / plafond de charge atteint
    if overflow_count > 0:
        state.banner_refs["heavy_el"].set_visibility(True)
        state.banner_refs["heavy"].set_text(
            f"{overflow_count} reportée{'s' if overflow_count > 1 else ''} — plafond atteint"
        )
    elif load.get("is_heavy"):
        state.banner_refs["heavy_el"].set_visibility(True)
        state.banner_refs["heavy"].set_text("Charge lourde")
    else:
        state.banner_refs["heavy_el"].set_visibility(False)
```

- [ ] **Step 3: Verify no syntax/import errors, then commit Tasks 4+5 together**

Run: `python -c "import ast; ast.parse(open('frontend/pages/dashboard/_banner.py', encoding='utf-8').read())"`
Expected: no output

Run: `python -c "from frontend.pages.dashboard import _banner, _reviews"`
Expected: no output / no exception

Run: `python -m pytest tests/ -v -k "not lisa_scraper"`
Expected: PASS, no regressions

```bash
git add frontend/pages/dashboard/_reviews.py frontend/pages/dashboard/_banner.py
git commit -m "$(cat <<'EOF'
feat(dashboard): enforce daily_budget_min and surface it in the banner

rebuild_all() now trims urgent+today to the user's daily_budget_min
(minutes) before rendering, using apply_daily_budget — cut items keep
their due_date and roll over to the next day automatically. The
banner gains a new pill: "N reportée(s) — plafond atteint" when the
budget cut something, or "Charge lourde" when compute_daily_load
flags is_heavy against the user's own threshold (falls back to the
existing 120min default when no budget is set).
EOF
)"
```

- [ ] **Step 4: Manual browser verification (end-to-end)**

Start the app, then:
1. Go to `/settings`, set "Charge max quotidienne" to a low value (e.g. `30`).
2. Go to the dashboard. Confirm the RETARD/AUJOURD'HUI sections show fewer items than before, and that "Voir X de plus" (if present) only reveals a bounded remainder consistent with the budget.
3. Confirm the banner shows the amber "N reportée(s) — plafond atteint" pill when items were cut.
4. Reset "Charge max quotidienne" to `0` in Settings, reload the dashboard, confirm behavior returns to today's baseline (no pill, full list truncated only by the existing 5/8 + "voir plus" mechanism).

---

## Post-Implementation

Once all 5 tasks are done and the manual verification in Task 5 Step 4 passes, this closes the gap described in the spec: the dashboard can no longer feel "infinite" once the user sets a budget, and defaults to today's exact behavior when they don't.
