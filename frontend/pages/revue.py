"""revue.py — Vue « Revue hebdo » (refonte, session 13, écran nouveau).

Bandeau (temps + delta vs semaine dernière, items consolidés/régressés,
révisions faites) + deux colonnes (Consolidé cette semaine / A régressé) +
bloc Focus semaine prochaine. N'existe pas côté classic (README :
« pages/revue.py, nouveau ») — contenu invariant, seul `frame()` fait
varier le chrome.

Source de données : `backend/core/analytics/weekly_report.py`
(`generate_weekly_report`), déjà écrit mais jamais routé nulle part avant
cette session (ni `/bilan`, ni ailleurs) — voir Journal du CLAUDE.md de la
refonte pour la découverte faite à l'étape 12. `bilan.py` (Bilan hebdo
classic, lui aussi jamais routé) répond à une question différente
(objectifs personnalisables vs snapshot réel), non touché.

Écarts assumés :
  • `WeeklyReport.courses_improved`/`courses_regressed` ne donnent que des
    course_id, pas les scores avant/après affichés dans la capture
    (« 52 → 61 ») — requête `mastery_snapshots` dupliquée localement
    (mêmes tables/semaines que `generate_weekly_report`) pour récupérer les
    deux scores, plutôt que de modifier le backend ;
  • « Focus semaine prochaine » = les 3 catégories de lacunes actives les
    plus fréquentes (`WeeklyReport.top_weak_categories`, déjà calculé) —
    aucun moteur de suggestion n'existe, README ne précise pas la source ;
  • « Planifier ce focus » route vers `/planning` (pas de moteur de
    planification dédié à un focus, même logique que « Lancer la série
    adaptative » sur Détail item routant vers `/qcm`, session 4).
"""
from __future__ import annotations

import datetime

from nicegui import ui

from frontend.theme import frame
from backend.state.store import data_store
from backend.core.reviews.local_store import _conn
from backend.core.analytics.weekly_report import generate_weekly_report, _week_iso

_MONTHS_FR = ["jan", "fév", "mar", "avr", "mai", "juin",
              "juil", "août", "sep", "oct", "nov", "déc"]

_CSS = """
.rh-wrap { max-width:none; width:100%; align-items:stretch; }
.rh-topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; padding:4px 0 18px; flex-wrap:wrap; }
.rh-title { font-size:20px; font-weight:600; color:var(--text); letter-spacing:-0.01em; }
.rh-subtitle { font-size:12.5px; color:var(--text-muted); margin-top:4px; }
.rh-nav { display:flex; gap:8px; }
.rh-btn { display:inline-flex; align-items:center; gap:6px; height:32px; padding:0 14px; border-radius:6px;
  font-size:12.5px; font-weight:500; cursor:pointer; border:1px solid var(--border); background:var(--bg);
  color:var(--text) !important; white-space:nowrap;
  transition: background var(--duration-fast) var(--ease-standard), border-color var(--duration-fast) var(--ease-standard); }
.rh-btn:hover { background:var(--surface); border-color:var(--border-strong); }
.rh-btn.disabled { opacity:.4; cursor:default; pointer-events:none; }
.rh-btn.primary { background:var(--accent); border-color:var(--accent); color:var(--accent-text) !important; }
.rh-btn.primary:hover { background:var(--accent-hover); }
.rh-summary { display:flex; align-items:center; gap:24px; padding:14px 0; border-top:1px solid var(--border);
  border-bottom:1px solid var(--border); margin-bottom:20px; flex-wrap:wrap; }
.rh-metric { display:flex; flex-direction:column; gap:2px; }
.rh-metric-val { font-size:24px; font-weight:700; line-height:1; color:var(--text); }
.rh-metric-sub { font-size:11.5px; color:var(--text-muted); }
.rh-vsep { width:1px; height:34px; background:var(--border); }
.rh-cols { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:20px; }
@media (max-width: 700px) { .rh-cols { grid-template-columns:1fr; } }
.rh-card { border:1px solid var(--border); border-radius:8px; padding:14px; }
.rh-card-head { display:flex; align-items:center; gap:7px; font-size:12.5px; font-weight:600; color:var(--text); margin-bottom:10px; }
.rh-card-dot { width:7px; height:7px; border-radius:50%; flex:0 0 7px; }
.rh-item-row { display:flex; align-items:center; gap:10px; height:32px; }
.rh-item-id { font-family:var(--font-mono); font-size:11px; color:var(--text-dim); flex:0 0 34px; }
.rh-item-title { flex:1 1 auto; min-width:0; font-size:12.5px; color:var(--text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.rh-item-trans { font-family:var(--font-mono); font-size:11.5px; font-weight:600; flex:0 0 auto; white-space:nowrap; }
.rh-card-empty { font-size:12px; color:var(--text-dim); font-style:italic; padding:6px 0; }
.rh-focus { background:var(--accent-wash); border-radius:8px; padding:14px 16px; }
.rh-focus-label { font-family:var(--font-mono); font-size:10.5px; letter-spacing:.04em; color:var(--text-muted); margin-bottom:10px; }
.rh-focus-item { display:flex; align-items:center; gap:8px; height:26px; font-size:12.5px; color:var(--text); }
.rh-focus-dot { width:6px; height:6px; border-radius:50%; background:var(--warning); flex:0 0 6px; }
.rh-focus-empty { font-size:12px; color:var(--text-muted); font-style:italic; padding:4px 0 10px; }
.rh-focus-btn { margin-top:10px; }
"""


def _score_transitions(week_start: datetime.date) -> tuple[list[tuple], list[tuple]]:
    """Rejoue la comparaison de mastery_snapshots de generate_weekly_report,
    mais conserve les scores avant/après (le dataclass WeeklyReport ne
    garde que les course_id, pas les valeurs)."""
    week_str = _week_iso(week_start)
    prev_week_str = _week_iso(week_start - datetime.timedelta(weeks=1))
    with _conn() as con:
        snap_cur = {
            r["course_id"]: r["mastery_score"]
            for r in con.execute(
                "SELECT course_id, mastery_score FROM mastery_snapshots WHERE week = ?",
                (week_str,)).fetchall()
        }
        snap_prev = {
            r["course_id"]: r["mastery_score"]
            for r in con.execute(
                "SELECT course_id, mastery_score FROM mastery_snapshots WHERE week = ?",
                (prev_week_str,)).fetchall()
        }
    improved, regressed = [], []
    for cid, cur in snap_cur.items():
        prev = snap_prev.get(cid)
        if prev is None or cur is None:
            continue
        if cur > prev:
            improved.append((cid, prev, cur))
        elif cur < prev:
            regressed.append((cid, prev, cur))
    improved.sort(key=lambda t: -(t[2] - t[1]))
    regressed.sort(key=lambda t: (t[2] - t[1]))
    return improved, regressed


def _fmt_hours(hours: float) -> str:
    total_min = round(hours * 60)
    h, m = divmod(total_min, 60)
    return f"{h}h{m:02d}" if h else f"{m} min"


@ui.page('/revue')
@frame('Revue hebdo')
def revue_page() -> None:
    if not data_store.is_loaded:
        ui.label("Chargement des données…").classes("text-slate-500")
        return

    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)

    course_map = {c.id: c for c in data_store.cours}
    state = {"weeks_back": 0}

    with ui.column().classes("rh-wrap gap-0"):
        topbar = ui.element("div").classes("rh-topbar")
        summary = ui.element("div").classes("rh-summary")
        cols = ui.element("div").classes("rh-cols")
        focus_box = ui.column().classes("w-full")

    def _default_week_start() -> datetime.date:
        today = datetime.date.today()
        return today - datetime.timedelta(days=today.weekday() + 7)

    def _current_week_start() -> datetime.date:
        return _default_week_start() - datetime.timedelta(weeks=state["weeks_back"])

    def _go_back() -> None:
        state["weeks_back"] += 1
        _render()

    def _go_forward() -> None:
        if state["weeks_back"] > 0:
            state["weeks_back"] -= 1
            _render()

    def _draw_topbar(week_start: datetime.date, week_end: datetime.date) -> None:
        topbar.clear()
        if week_start.month == week_end.month:
            range_txt = f"{week_start.day} au {week_end.day} {_MONTHS_FR[week_end.month - 1]}"
        else:
            range_txt = (
                f"{week_start.day} {_MONTHS_FR[week_start.month - 1]} "
                f"au {week_end.day} {_MONTHS_FR[week_end.month - 1]}"
            )
        with topbar:
            with ui.column().classes("gap-0"):
                ui.label("Revue hebdo").classes("rh-title")
                ui.label(f"Semaine du {range_txt} · générée automatiquement").classes("rh-subtitle")
            with ui.element("div").classes("rh-nav"):
                prev_btn = ui.element("div").classes("rh-btn")
                with prev_btn:
                    ui.label("‹ Semaine précédente")
                prev_btn.on("click", _go_back)

                next_btn = ui.element("div").classes(
                    "rh-btn" if state["weeks_back"] > 0 else "rh-btn disabled")
                with next_btn:
                    ui.label("Semaine suivante ›")
                if state["weeks_back"] > 0:
                    next_btn.on("click", _go_forward)

    def _draw_summary(report, delta_hours: float | None) -> None:
        summary.clear()
        with summary:
            with ui.element("div").classes("rh-metric"):
                ui.label(_fmt_hours(report.total_hours)).classes("rh-metric-val")
                if delta_hours is not None and abs(delta_hours) >= 0.05:
                    sign = "+" if delta_hours > 0 else "−"
                    ui.label(f"travaillé · {sign}{_fmt_hours(abs(delta_hours))} vs sem. dernière").classes("rh-metric-sub")
                else:
                    ui.label("travaillé").classes("rh-metric-sub")

            ui.element("div").classes("rh-vsep")

            n_improved = len(report.courses_improved)
            with ui.element("div").classes("rh-metric"):
                ui.label(f"+{n_improved}").classes("rh-metric-val").style("color:var(--success)")
                ui.label("items consolidés").classes("rh-metric-sub")

            ui.element("div").classes("rh-vsep")

            n_regressed = len(report.courses_regressed)
            with ui.element("div").classes("rh-metric"):
                ui.label(f"−{n_regressed}").classes("rh-metric-val").style("color:var(--danger)")
                ui.label("items en régression").classes("rh-metric-sub")

            ui.element("div").classes("rh-vsep")

            with ui.element("div").classes("rh-metric"):
                ui.label(str(report.sessions_count)).classes("rh-metric-val")
                ui.label("révisions faites").classes("rh-metric-sub")

    def _draw_transition_card(title: str, dot_color: str, items: list[tuple], trans_color: str) -> None:
        with ui.element("div").classes("rh-card"):
            with ui.element("div").classes("rh-card-head"):
                ui.element("span").classes("rh-card-dot").style(f"background:{dot_color}")
                ui.label(title)
            if not items:
                ui.label("Rien à signaler cette semaine.").classes("rh-card-empty")
                return
            for cid, prev, cur in items[:8]:
                course = course_map.get(cid)
                with ui.element("div").classes("rh-item-row"):
                    ui.label(course.item_number if course and course.item_number else "—").classes("rh-item-id")
                    ui.label(course.title if course else cid).classes("rh-item-title")
                    ui.label(f"{prev} → {cur}").classes("rh-item-trans").style(f"color:{trans_color}")

    def _draw_cols(improved: list[tuple], regressed: list[tuple]) -> None:
        cols.clear()
        with cols:
            _draw_transition_card("Consolidé cette semaine", "var(--success)", improved, "var(--success)")
            _draw_transition_card("A régressé (oubli)", "var(--danger)", regressed, "var(--danger)")

    def _draw_focus(report) -> None:
        focus_box.clear()
        with focus_box:
            with ui.element("div").classes("rh-focus"):
                ui.label("FOCUS SEMAINE PROCHAINE").classes("rh-focus-label")
                top = report.top_weak_categories[:3]
                if not top:
                    ui.label("Aucune lacune active à prioriser — continue comme ça.").classes("rh-focus-empty")
                else:
                    for category, count in top:
                        with ui.element("div").classes("rh-focus-item"):
                            ui.element("span").classes("rh-focus-dot")
                            ui.label(f"{category} ({count} lacune{'s' if count != 1 else ''} active{'s' if count != 1 else ''})")
                btn = ui.element("div").classes("rh-btn primary rh-focus-btn")
                with btn:
                    ui.label("Planifier ce focus")
                btn.on("click", lambda: ui.navigate.to("/planning"))

    def _render() -> None:
        week_start = _current_week_start()
        week_end = week_start + datetime.timedelta(days=6)
        report = generate_weekly_report(week_start=week_start)
        prev_report = generate_weekly_report(week_start=week_start - datetime.timedelta(weeks=1))
        delta_hours = report.total_hours - prev_report.total_hours

        improved, regressed = _score_transitions(week_start)

        _draw_topbar(week_start, week_end)
        _draw_summary(report, delta_hours)
        _draw_cols(improved, regressed)
        _draw_focus(report)

    _render()
