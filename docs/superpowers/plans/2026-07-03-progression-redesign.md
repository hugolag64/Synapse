# Progression Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `frontend/pages/stats.py` ("Ma Progression", route `/stats`) the same visual polish as the recently redesigned QCM page — hero banner, KPI cards with sparklines, a new mastery-distribution overview — while keeping its existing 3-tab structure and all current data/behavior unchanged.

**Architecture:** Extract the two visual building blocks QCM already proved (`.qcm-hero` / `.qcm-kpi-card` / `.qcm-ring` CSS + the `_sparkline_svg` helper) into shared, page-agnostic names and a shared component module, then reuse them on `stats.py`. Add one new pure-Python aggregation (`_get_all_mastery_snapshots`) that both a new KPI (avg. mastery score) and a new mastery-distribution bar draw from, computed once per render. Restyle the 3 existing tabs to the same token system without touching their logic.

**Tech Stack:** Python 3, NiceGUI, Tailwind utility classes + a small custom CSS design-token layer in `static/synapse.css` (`--s-*` variables), SQLite via `backend/core/reviews/local_store.py`.

## Global Constraints

- No new backend functions and no changes to `backend/core/reviews/local_store.py` or `backend/core/reviews/mastery.py` (spec section 5 / hors-scope).
- No automated tests for UI pages in this project (established convention, confirmed in spec section 6) — verification is a Python import/syntax check per task plus a full manual browser check (light + dark mode) in the final task.
- `frontend/pages/qcm.py` must render identically after Task 1 — only class names change, no visual difference.
- Every color used must come from an existing token: `static/synapse.css` `--s-*` variables, or the existing `PROGRESSION_COLORS` / `_ACCENT_HEX` maps. No new hex values invented for mastery levels.
- App runs via `python main.py` on `127.0.0.1:8082` with `reload=True` in dev — editing a file under `frontend/`/`backend/`/`static/` auto-reloads the running server; no manual restart needed if it's already running.

---

## File Structure

| File | Responsibility |
|---|---|
| `static/synapse.css` | Rename `.qcm-*` shared classes to `.synapse-*`; add `.synapse-panel` (generic white/dark card token wrapper, replaces repeated Tailwind utility soup in `stats.py`). |
| `frontend/components/sparkline.py` (new) | `sparkline_svg()` — pure function, moved out of `qcm.py` so both pages can import it. |
| `frontend/pages/qcm.py` | Update the 5 call sites that reference renamed classes / the moved sparkline function. No visual change. |
| `frontend/pages/stats.py` | Hero banner, KPI row, mastery-distribution bar, and per-tab restyling. All changes live here. |

---

### Task 1: Shared CSS rename + extract sparkline helper

**Files:**
- Modify: `static/synapse.css:1165-1245`
- Create: `frontend/components/sparkline.py`
- Modify: `frontend/pages/qcm.py:100-119` (remove `_sparkline_svg`, import shared one), `:139`, `:164`, `:183`, `:186`, `:879`

**Interfaces:**
- Produces: `frontend.components.sparkline.sparkline_svg(values: list[float], color: str, width: int = 60, height: int = 28) -> str` — used by Task 2.
- Produces CSS classes for later tasks: `.synapse-hero`, `.synapse-kpi-card` (with `--card-accent` custom prop), `.synapse-ring` / `.synapse-ring-label` (with `--ring-pct` / `--ring-color`), `.synapse-spark`, `.synapse-panel`.

- [ ] **Step 1: Create the shared sparkline component**

Create `frontend/components/sparkline.py`:

```python
"""sparkline.py — mini SVG sparkline, shared by QCM and Progression pages."""
from __future__ import annotations


def sparkline_svg(values: list[float], color: str, width: int = 60, height: int = 28) -> str:
    """Mini sparkline SVG (polyline) — valeurs en ordre chronologique."""
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    rng = (hi - lo) or 1
    step = width / (len(values) - 1)
    pts = []
    for i, v in enumerate(values):
        x = i * step
        y = height - ((v - lo) / rng) * (height - 6) - 3
        pts.append(f"{x:.1f},{y:.1f}")
    points = " ".join(pts)
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        f'</svg>'
    )
```

- [ ] **Step 2: Verify the new module imports cleanly**

Run: `python -c "from frontend.components.sparkline import sparkline_svg; print(sparkline_svg([1,2,3], '#2563EB'))"`
Expected: prints an `<svg ...>...</svg>` string, no traceback.

- [ ] **Step 3: Rename the CSS classes in `static/synapse.css`**

In the block currently spanning lines 1165-1245 (`QCM PAGE REDESIGN` section), replace every occurrence of the 5 class names below (selector name only — keep all property values, dark-mode overrides, and the surrounding comments untouched):

- `.qcm-hero` → `.synapse-hero` (and `body.body--dark .qcm-hero` → `body.body--dark .synapse-hero`)
- `.qcm-kpi-card` → `.synapse-kpi-card` (both the base rule, `:hover`, and the dark override)
- `.qcm-ring` → `.synapse-ring` (base rule and `::after`, plus `body.body--dark .qcm-ring::after`)
- `.qcm-ring-label` → `.synapse-ring-label`
- `.qcm-spark` → `.synapse-spark`

Do **not** touch `.qcm-combo-card`, `.qcm-combo-chart`, `.qcm-combo-errors`, `.qcm-filter-*`, `.qcm-item-row*`, `.qcm-sort-header` — those stay QCM-specific.

Then add a new generic panel class right after the renamed `.synapse-spark` block:

```css
/* ── Generic panel (white/dark card wrapper) ──────────────────── */
.synapse-panel {
  border-radius: var(--s-r-xl);
  border: 1px solid var(--s-border);
  background: #FFFFFF;
  box-shadow: var(--s-shadow-sm);
}
body.body--dark .synapse-panel {
  background: #111827;
  border-color: #1E2D3D;
}
```

- [ ] **Step 4: Update `frontend/pages/qcm.py` to use the renamed classes and the shared sparkline import**

Remove the local `_sparkline_svg` definition (lines 100-119) and its `# ── KPI Cards ──...` comment line above it if it becomes redundant, and add the import instead:

```python
from frontend.components.sparkline import sparkline_svg
```

(add this import near the top with the other `frontend.*` imports, e.g. right after `from frontend.theme import frame`)

Update the 4 remaining call sites:
- Line ~139: `with ui.element("div").classes("qcm-kpi-card w-full")...` → `.classes("synapse-kpi-card w-full")`
- Line ~164: `ui.html(_sparkline_svg(_vals, _col), sanitize=False).classes("qcm-spark")` → `ui.html(sparkline_svg(_vals, _col), sanitize=False).classes("synapse-spark")`
- Line ~183: `.classes("qcm-ring")` → `.classes("synapse-ring")`
- Line ~186: `.classes("qcm-ring-label")` → `.classes("synapse-ring-label")`
- Line ~879: `.classes("qcm-hero w-full")` → `.classes("synapse-hero w-full")`

- [ ] **Step 5: Verify `qcm.py` still imports cleanly**

Run: `python -c "import ast; ast.parse(open('frontend/pages/qcm.py', encoding='utf-8').read())"`
Expected: no output, exit code 0 (syntax valid). Then run: `python -c "from frontend.pages.qcm import qcm_page"` — expected: no traceback (catches missing-import errors from the rename).

- [ ] **Step 6: Manual visual spot-check on QCM**

If the app is running (`127.0.0.1:8082`), open `/qcm` in a browser and confirm the hero banner, the 3 KPI cards (with sparkline/ring), and dark mode all look exactly as before the rename (no visual diff expected — only class names changed).

- [ ] **Step 7: Commit**

```bash
git add static/synapse.css frontend/components/sparkline.py frontend/pages/qcm.py
git commit -m "refactor: extract shared sparkline helper and generic synapse-* CSS classes from QCM page"
```

---

### Task 2: Hero banner + KPI row on Progression

**Files:**
- Modify: `frontend/pages/stats.py` (add imports, add `_get_all_mastery_snapshots`, `_compute_kpis`, `_render_kpi_row`; wire into `stats_page()`)

**Interfaces:**
- Consumes: `frontend.components.sparkline.sparkline_svg(values, color, width=60, height=28) -> str` (Task 1); `local_store.get_weekly_study_stats(days) -> dict` with keys `total_minutes`, `session_count` (existing); `local_store.get_recent_study_sessions(limit) -> list[sqlite3.Row]` with `session_date`, `duration_minutes` columns (existing); `local_store.get_streak_days() -> int` (existing); `mastery.get_course_mastery(course, context, sessions, total_postpone) -> CourseProgressSnapshot` with `.score: int | None`, `.level: str` (existing).
- Produces: `_get_all_mastery_snapshots() -> list[tuple[CourseProgressSnapshot, course]]` — used by Task 3. `_compute_kpis(days: int, snapshots: list) -> dict` with keys `total_minutes`, `session_count`, `minutes_series`, `sessions_series`, `avg_score`, `tracked_count`, `streak` — used only within this task's `render()` closure.

- [ ] **Step 1: Add the new imports at the top of `frontend/pages/stats.py`**

After the existing `from frontend.components.course_quick_actions import open_quick_session_dialog` line, add:

```python
from frontend.components.sparkline import sparkline_svg
```

- [ ] **Step 2: Add `_get_all_mastery_snapshots()` near the existing `_get_fragile_courses` helper**

Insert this function directly before `_get_fragile_courses` (around line 65):

```python
def _get_all_mastery_snapshots() -> list[tuple]:
    """Snapshot de maîtrise pour tous les cours (y compris non commencés).
    Contrairement à _get_fragile_courses, ne filtre rien : sert de base
    commune au score moyen (KPI) et à la répartition par niveau."""
    if not data_store.cours:
        return []
    try:
        sessions_map = local_store.get_sessions_by_course()
        postpone_map = local_store.get_postpone_counts()
    except Exception as exc:
        logger.warning(f"mastery snapshots load: {exc}")
        return []

    results = []
    for course in data_store.cours:
        try:
            sessions = sessions_map.get(course.id, [])
            snap = get_course_mastery(
                course, context="college", sessions=sessions,
                total_postpone=postpone_map.get(course.id, 0),
            )
        except Exception:
            continue
        results.append((snap, course))
    return results
```

- [ ] **Step 3: Add `_compute_kpis()` after `_get_all_mastery_snapshots`**

```python
def _compute_kpis(days: int, snapshots: list) -> dict:
    stats = local_store.get_weekly_study_stats(days=days)

    sessions = local_store.get_recent_study_sessions(limit=200)
    if days > 0:
        cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        sessions = [s for s in sessions if (_get(s, "session_date") or "") >= cutoff]

    daily_minutes: dict[str, int] = defaultdict(int)
    daily_counts: dict[str, int] = defaultdict(int)
    for s in sessions:
        d = _get(s, "session_date")
        if not d:
            continue
        daily_minutes[d] += _get(s, "duration_minutes", 0) or 0
        daily_counts[d] += 1

    days_sorted = sorted(daily_minutes.keys())
    minutes_series = [daily_minutes[d] for d in days_sorted]
    sessions_series = [daily_counts[d] for d in days_sorted]

    scores = [snap.score for snap, _ in snapshots if snap.score is not None]
    avg_score = round(sum(scores) / len(scores)) if scores else None

    return {
        "total_minutes": stats["total_minutes"],
        "session_count": stats["session_count"],
        "minutes_series": minutes_series,
        "sessions_series": sessions_series,
        "avg_score": avg_score,
        "tracked_count": len(scores),
        "streak": local_store.get_streak_days(),
    }
```

Note: `defaultdict` is already imported at the top of the file (`from collections import defaultdict`); `_get` is the existing helper at the top of the file.

- [ ] **Step 4: Add `_render_kpi_row()` after `_compute_kpis`**

```python
def _render_kpi_row(container, kpis: dict) -> None:
    container.clear()

    def _kpi(icon_name, label, value_txt, accent_hex, sub_txt, extra=None):
        with ui.element("div").classes("synapse-kpi-card w-full").style(
            f"--card-accent:{accent_hex}"
        ):
            if extra:
                extra()
            with ui.column().classes("gap-1 min-w-0 flex-1"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon(icon_name, size="xs").classes("text-slate-300")
                    ui.label(label).classes("text-xs text-slate-400 font-medium")
                ui.label(value_txt).classes(
                    "text-3xl font-extrabold tabular-nums leading-none text-slate-800 dark:text-slate-100"
                )
                ui.label(sub_txt).classes("text-xs text-slate-400")

    with container:
        # Temps d'étude
        def _time_spark(_vals=kpis["minutes_series"]):
            if len(_vals) >= 2:
                ui.html(
                    sparkline_svg(_vals, "#2563EB"), sanitize=False
                ).classes("synapse-spark")

        _kpi(
            "schedule", "Temps d'étude", _fmt_minutes(kpis["total_minutes"]),
            "#2563EB", f"{kpis['session_count']} séance(s)",
            extra=_time_spark if len(kpis["minutes_series"]) >= 2 else None,
        )

        # Séances
        def _sess_spark(_vals=kpis["sessions_series"]):
            if len(_vals) >= 2:
                ui.html(
                    sparkline_svg(_vals, "#2563EB"), sanitize=False
                ).classes("synapse-spark")

        _kpi(
            "event_repeat", "Séances", str(kpis["session_count"]),
            "#2563EB", "sur la période",
            extra=_sess_spark if len(kpis["sessions_series"]) >= 2 else None,
        )

        # Score de maîtrise moyen (ring)
        avg = kpis["avg_score"]
        ring_col = (
            "#22c55e" if avg is not None and avg >= 80
            else "#3B82F6" if avg is not None and avg >= 60
            else "#f97316" if avg is not None and avg >= 40
            else "#ef4444" if avg is not None
            else "#CBD5E1"
        )

        def _ring_extra(_pct=avg or 0, _col=ring_col):
            with ui.element("div").classes("synapse-ring").style(
                f"--ring-pct:{_pct};--ring-color:{_col}"
            ):
                ui.label(f"{_pct}%").classes("synapse-ring-label").style(f"color:{_col}")

        _kpi(
            "insights", "Score de maîtrise", f"{avg}%" if avg is not None else "—",
            ring_col, f"{kpis['tracked_count']} cours suivis",
            extra=_ring_extra if avg is not None else None,
        )

        # Série en cours (streak)
        streak = kpis["streak"]
        streak_col = "#f97316" if streak >= 3 else "#94A3B8"

        def _streak_extra(_col=streak_col):
            with ui.element("div").classes(
                "flex items-center justify-center rounded-full w-11 h-11 shrink-0"
            ).style(f"background:{_col}1A"):
                ui.icon("local_fire_department", size="sm").style(f"color:{_col}")

        _kpi(
            "local_fire_department", "Série en cours", f"{streak}j",
            streak_col, "jours consécutifs",
            extra=_streak_extra,
        )
```

- [ ] **Step 5: Wire the hero banner and KPI row into `stats_page()`**

Replace the current title block (lines 630-637):

```python
        with ui.row().classes("items-end justify-between w-full mb-2 flex-wrap gap-3"):
            with ui.column().classes("gap-0"):
                ui.label("Ma Progression").classes(
                    "text-2xl font-bold text-slate-900 dark:text-slate-100"
                )
                ui.label("Historique d'apprentissage · tendances · objectifs").classes(
                    "text-sm text-slate-400 mt-0.5"
                )
```

with:

```python
        with ui.element("div").classes("synapse-hero w-full mb-4"):
            with ui.column().classes("gap-0.5"):
                ui.label("Ma Progression").classes(
                    "text-2xl font-extrabold text-slate-900 dark:text-slate-50 tracking-tight"
                )
                ui.label("Historique d'apprentissage · tendances · objectifs").classes(
                    "text-sm text-slate-500 dark:text-slate-400 mt-0.5"
                )

        snapshots = _get_all_mastery_snapshots()
        kpi_container = ui.element("div").classes(
            "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 w-full mb-4"
        )
        _render_kpi_row(kpi_container, _compute_kpis(state.days, snapshots))
```

This must be placed after `state = SimpleNamespace(days=7)` and before the `ui.tabs()` block. `snapshots` and `kpi_container` need to be visible to the `set_period()` closure defined later in the Activité tab (Step 6), so keep them as local variables in `stats_page()`'s scope (they already will be, since `stats_page` is one function).

- [ ] **Step 6: Refresh the KPI row when the period selector changes**

In the existing `set_period()` function (inside the Activité tab panel, currently):

```python
                def set_period(d: int):
                    state.days = d
                    _rebuild_period_row()
                    render()
```

change it to also recompute the KPI row:

```python
                def set_period(d: int):
                    state.days = d
                    _rebuild_period_row()
                    _render_kpi_row(kpi_container, _compute_kpis(state.days, snapshots))
                    render()
```

- [ ] **Step 7: Verify the module imports and the page function is callable**

Run: `python -c "import ast; ast.parse(open('frontend/pages/stats.py', encoding='utf-8').read())"`
Expected: no output (valid syntax).

Run: `python -c "from frontend.pages.stats import stats_page, _compute_kpis, _get_all_mastery_snapshots, _render_kpi_row"`
Expected: no traceback.

- [ ] **Step 8: Manual visual check**

Open `/stats` in the browser. Confirm: hero banner renders, 4 KPI cards render with plausible values (time, sessions, mastery score with donut ring, streak with flame icon), sparklines appear on the first two cards if there are ≥2 days of session data, switching period (7j/30j/Tout) updates the KPI row.

- [ ] **Step 9: Commit**

```bash
git add frontend/pages/stats.py
git commit -m "feat: add hero banner and KPI row (time, sessions, mastery score, streak) to Progression page"
```

---

### Task 3: Mastery distribution bar

**Files:**
- Modify: `frontend/pages/stats.py` (add `_LEVEL_HEX`, `_render_mastery_distribution`; wire into `stats_page()`)

**Interfaces:**
- Consumes: `_get_all_mastery_snapshots()` (Task 2, already computed once as `snapshots` in `stats_page()`); `PROGRESSION_COLORS: dict[str, str]` from `backend.core.reviews.mastery` (existing, Quasar color names); `_ACCENT_HEX: dict[str, str]` from `frontend.components.course_card` (existing, Quasar color name → hex, already used for the CourseCard mastery dot).
- Produces: `_render_mastery_distribution(container, snapshots: list) -> None` — called once from `stats_page()`.

- [ ] **Step 1: Add the imports**

Add near the top of `frontend/pages/stats.py`, alongside the existing `from backend.core.reviews.mastery import get_course_mastery` line:

```python
from backend.core.reviews.mastery import get_course_mastery, PROGRESSION_COLORS
from frontend.components.course_card import _ACCENT_HEX
```

(replace the existing single-name import line with the two-name version above; add the `course_card` import as a new line right after it)

- [ ] **Step 2: Add the level→hex lookup and the render function**

Insert after `_get_all_mastery_snapshots` (before `_compute_kpis`):

```python
_LEVEL_HEX: dict[str, str] = {
    level: _ACCENT_HEX.get(color, "#94A3B8")
    for level, color in PROGRESSION_COLORS.items()
}
_LEVEL_ORDER = [
    "à préparer", "à lire", "en construction", "à consolider",
    "à entraîner", "fragile", "critique", "maîtrisé",
]


def _render_mastery_distribution(container, snapshots: list) -> None:
    container.clear()
    if not snapshots:
        return

    counts: dict[str, int] = defaultdict(int)
    for snap, _ in snapshots:
        counts[snap.level] += 1
    total = sum(counts.values())
    if not total:
        return

    with container:
        with ui.element("div").classes("synapse-panel w-full p-4"):
            ui.label("Répartition de la maîtrise").classes(
                "text-[11px] font-bold uppercase tracking-widest text-slate-400 mb-3"
            )
            with ui.element("div").classes(
                "flex w-full rounded-full overflow-hidden gap-px"
            ).style("height:10px"):
                for level in _LEVEL_ORDER:
                    cnt = counts.get(level, 0)
                    if not cnt:
                        continue
                    pct = max(cnt / total * 100, 2)
                    color = _LEVEL_HEX.get(level, "#94A3B8")
                    ui.element("div").style(
                        f"width:{pct}%;background:{color};flex-shrink:0"
                    ).tooltip(f"{cnt} cours · {level.capitalize()}")

            with ui.row().classes("flex-wrap gap-x-4 gap-y-1.5 mt-3"):
                for level in _LEVEL_ORDER:
                    cnt = counts.get(level, 0)
                    if not cnt:
                        continue
                    color = _LEVEL_HEX.get(level, "#94A3B8")
                    with ui.row().classes("items-center gap-1.5 cursor-pointer").on(
                        "click", lambda: ui.navigate.to("/colleges")
                    ):
                        ui.element("div").classes("w-2 h-2 rounded-full shrink-0").style(
                            f"background:{color}"
                        )
                        ui.label(f"{level.capitalize()} ({cnt})").classes(
                            "text-[11px] text-slate-500 dark:text-slate-400"
                        )
```

- [ ] **Step 3: Wire it into `stats_page()`**

Right after the KPI row wiring added in Task 2 Step 5 (`_render_kpi_row(kpi_container, _compute_kpis(state.days, snapshots))`), add:

```python
        mastery_container = ui.element("div").classes("w-full mb-4")
        _render_mastery_distribution(mastery_container, snapshots)
```

- [ ] **Step 4: Verify imports**

Run: `python -c "from frontend.pages.stats import _render_mastery_distribution, _LEVEL_HEX, _LEVEL_ORDER"`
Expected: no traceback. This also confirms the `_ACCENT_HEX` import from `course_card` resolved correctly.

- [ ] **Step 5: Manual visual check**

Open `/stats`. Confirm a horizontal segmented bar appears below the KPI row, with a legend underneath showing each present mastery level and its course count; hovering a segment shows a tooltip; clicking a segment or a legend item navigates to `/colleges`.

- [ ] **Step 6: Commit**

```bash
git add frontend/pages/stats.py
git commit -m "feat: add mastery distribution bar to Progression page"
```

---

### Task 4: Remove the stats accordion from the Activité tab

**Files:**
- Modify: `frontend/pages/stats.py:225-283` (delete `_render_stats_accordion`), `:664-666` (stop calling it)

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new (pure deletion — the 4 stats it showed, temps/séances/confiance/pièges, are now redundant with the hero KPI row for temps/séances; confiance and pièges remain visible per-event in the timeline below, per spec section 4).

- [ ] **Step 1: Delete `_render_stats_accordion`**

Remove the entire function `_render_stats_accordion` (the block from `# ── Section 2 : Stats accordion ──...` comment through the end of the function, lines ~223-283 in the current file).

- [ ] **Step 2: Stop calling it from `render()`**

In the `render()` closure inside the Activité tab panel, change:

```python
                    content.clear()
                    with content:
                        _render_stats_accordion(stats)
                        with ui.element("div").classes(
                            "w-full rounded-2xl border border-slate-100 dark:border-slate-800 "
                            "bg-white dark:bg-slate-900 shadow-sm p-5"
                        ):
                            ui.label("Activité").classes(
                                "text-[11px] font-bold uppercase tracking-widest text-slate-400 mb-1"
                            )
                            _render_timeline(sessions, wps, render)
```

to:

```python
                    content.clear()
                    with content:
                        with ui.element("div").classes("synapse-panel w-full p-5"):
                            ui.label("Activité").classes(
                                "text-[11px] font-bold uppercase tracking-widest text-slate-400 mb-1"
                            )
                            _render_timeline(sessions, wps, render)
```

(this also folds in the token-based panel styling from `.synapse-panel` instead of the ad hoc Tailwind combo, per spec section 4)

- [ ] **Step 3: Verify**

Run: `python -c "from frontend.pages.stats import stats_page"`
Expected: no traceback (confirms `_render_stats_accordion` isn't referenced anywhere else — if it were, this would raise `NameError` only at call time, so also grep to be sure).

Run: `grep -n "_render_stats_accordion" frontend/pages/stats.py`
Expected: no output (zero matches).

- [ ] **Step 4: Manual visual check**

Open `/stats` → Activité tab. Confirm there's no collapsed "Statistiques de la période" accordion anymore, and the timeline renders directly below the mastery distribution bar with the `.synapse-panel` look (white/dark card, consistent rounded corners and shadow).

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/stats.py
git commit -m "refactor: remove redundant stats accordion from Activité tab (superseded by hero KPI row)"
```

---

### Task 5: Restyle the "À retravailler" tab

**Files:**
- Modify: `frontend/pages/stats.py` (`_render_fragile_banner`, `_render_fragile_card`)

**Interfaces:**
- Consumes: nothing new (same `fragile: list[tuple[snap, course]]` input as today).
- Produces: nothing new — pure visual change, no signature change, so `render_fragiles()` in `stats_page()` keeps calling it exactly as before.

- [ ] **Step 1: Align the fragile banner's radius/shadow to tokens**

In `_render_fragile_banner`, change the outer wrapper from:

```python
    with ui.element("div").classes(
        f"w-full rounded-2xl border border-{border_col}-200 dark:border-{border_col}-800 "
        f"bg-{border_col}-50 dark:bg-{border_col}-900/10 p-4"
    ):
```

to:

```python
    with ui.element("div").classes(
        f"w-full border border-{border_col}-200 dark:border-{border_col}-800 "
        f"bg-{border_col}-50 dark:bg-{border_col}-900/10 p-4"
    ).style("border-radius: var(--s-r-xl)"):
```

(the semantic red/orange background and border colors stay Tailwind classes — they encode urgency, not theme — only the radius becomes a token, matching spec section 4's "À retravailler" note)

- [ ] **Step 2: Align the fragile card's radius/shadow to tokens**

In `_render_fragile_card`, change:

```python
    with ui.element("div").classes(
        f"flex-shrink-0 w-44 rounded-xl border {border_cls} "
        "bg-white dark:bg-slate-900 shadow-sm p-3 flex flex-col gap-2"
    ):
```

to:

```python
    with ui.element("div").classes(
        f"flex-shrink-0 w-44 border {border_cls} "
        "bg-white dark:bg-slate-900 p-3 flex flex-col gap-2"
    ).style("border-radius: var(--s-r-lg); box-shadow: var(--s-shadow-sm)"):
```

- [ ] **Step 3: Verify**

Run: `python -c "from frontend.pages.stats import _render_fragile_banner, _render_fragile_card"`
Expected: no traceback.

- [ ] **Step 4: Manual visual check**

Open `/stats` → "À retravailler" tab (with at least one fragile/critique course in the data, or accept the empty state). Confirm the banner and the fragile cards still show the same red/orange urgency coloring as before, with corners/shadow now matching the same rounding used elsewhere on the page.

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/stats.py
git commit -m "style: align À retravailler tab radius/shadow to synapse design tokens"
```

---

### Task 6: Restyle the "Objectifs" tab

**Files:**
- Modify: `frontend/pages/stats.py` (`_render_semaine_tab` — the "Belle semaine" badge and the "Progression des objectifs" card)

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — pure visual change inside `_render_semaine_tab`, called exactly as before from `stats_page()`.

- [ ] **Step 1: Align the weekly badge's radius**

In `_render_sem`, both branches that build the badge (`"Aucune séance..."` info box and the `"Belle semaine !"` / `"X/4 objectifs..."` box) currently use `rounded-2xl`:

```python
                with ui.element("div").classes(
                    "w-full p-4 rounded-2xl border border-blue-100 dark:border-blue-800 "
                    "bg-blue-50 dark:bg-blue-900/10 flex items-center gap-3"
                ):
```

and

```python
                with ui.element("div").classes(
                    f"w-full p-4 rounded-2xl border border-{_col}-100 dark:border-{_col}-800 "
                    f"bg-{_col}-50 dark:bg-{_col}-900/10 flex items-center gap-4"
                ):
```

Replace `rounded-2xl` with nothing in the class string and add `.style("border-radius: var(--s-r-2xl)")` to each `ui.element("div")` call (keep every other class as-is — the semantic blue/green/orange coloring stays, only the radius becomes a token).

- [ ] **Step 2: Align the "Progression des objectifs" card**

Change:

```python
            with ui.card().classes("w-full p-4 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-800"):
```

to:

```python
            with ui.card().classes("w-full p-4 border border-slate-100 dark:border-slate-800").style(
                "border-radius: var(--s-r-2xl); box-shadow: var(--s-shadow-sm)"
            ):
```

- [ ] **Step 3: Verify**

Run: `python -c "from frontend.pages.stats import _render_semaine_tab"`
Expected: no traceback.

- [ ] **Step 4: Manual visual check**

Open `/stats` → "Objectifs" tab. Confirm the weekly badge and the "Progression des objectifs" card still show their existing semantic colors (blue/green/orange per goal status, indigo/blue/purple/green per metric), with rounding/shadow now consistent with the rest of the page.

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/stats.py
git commit -m "style: align Objectifs tab radius/shadow to synapse design tokens"
```

---

### Task 7: Full manual verification pass

**Files:** none (verification only)

**Interfaces:** none

- [ ] **Step 1: Confirm the app is running**

Run: `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8082/stats`
Expected: `200`. If not running, start it: `python main.py` (background) and re-check.

- [ ] **Step 2: Browser check — light mode**

Open `http://127.0.0.1:8082/stats`. Walk through: hero banner renders; 4 KPI cards show plausible values; mastery distribution bar renders with a legend; switch 7j/30j/Tout and confirm the KPI row updates; open each of the 3 tabs (Activité, À retravailler, Objectifs) and confirm no console errors and no visual regression versus Task 1-6 expectations.

- [ ] **Step 3: Browser check — dark mode**

Toggle dark mode (Paramètres → or existing dark-mode toggle) and repeat the same walkthrough on `/stats`. Confirm all new elements (hero, KPI cards, ring, sparklines, distribution bar, panels) have legible contrast in dark mode (they inherit `--s-*` dark overrides already defined in Task 1, so this should require no further code changes — this step is a regression check, not expected to require fixes).

- [ ] **Step 4: Confirm QCM is unaffected**

Open `http://127.0.0.1:8082/qcm` in both light and dark mode. Confirm it looks identical to before this plan (Task 1 only renamed classes, no visual change expected).

- [ ] **Step 5: Final commit (only if Step 3 or 4 required fixes)**

If any dark-mode contrast issue or QCM regression was found and fixed:

```bash
git add frontend/pages/stats.py frontend/pages/qcm.py static/synapse.css
git commit -m "fix: address dark-mode/QCM regressions found in Progression redesign verification"
```

If no fixes were needed, skip this step — the redesign is complete as of Task 6's commit.
