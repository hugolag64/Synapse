"""stats_cockpit.py — Vue « Statistiques » cockpit (refonte, session 12).

Vue principale de l'écran Statistiques.
stats.py). Bandeau (temps travaillé · révisions faites · maîtrise moyenne)
+ toggle 7j/30j/Tout + « Temps par collège » (barres) + « Activité récente »
(timeline). Le chemin classic (bandeau fragiles + onglets Activité/À
retravailler/Objectifs) reste strictement inchangé.

Écarts assumés (voir Journal du CLAUDE.md de la refonte) :
  • réutilise `_get_all_mastery_snapshots`/`_compute_kpis` du classic pour
    la maîtrise moyenne et le temps/séances (mêmes formules exactes) ;
  • réutilise `_fmt_minutes`/`_fmt_activities`/`_day_label`/`_get` pour la
    timeline (mise en forme identique au classic, restylée en tokens) ;
  • « Temps par collège » n'existe nulle part côté backend — agrégé ici
    depuis `get_recent_study_sessions` + une table course_id→collège
    construite localement (aucun agrégat SQL dédié) ;
  • timeline = séances uniquement (pas de fusion avec la création de
    lacunes comme le fait le classic `_render_timeline`) — le README §10
    et la capture ne montrent que des lignes d'activité, pas de lacunes.
"""
from __future__ import annotations

import datetime

from nicegui import ui

from backend.core.reviews import local_store
from backend.state.store import data_store
from frontend.pages.stats import (
    _get, _fmt_minutes, _fmt_activities, _day_label,
    _get_all_mastery_snapshots, _compute_kpis,
)
from frontend.components.mastery_indicator import _LEVEL_COLOR, _level_from_score

_CSS = """
.st-wrap { max-width:none; width:100%; align-items:stretch; }
.st-topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; padding:4px 0 18px; flex-wrap:wrap; }
.st-title { font-size:20px; font-weight:600; color:var(--text); letter-spacing:-0.01em; }
.st-subtitle { font-size:12.5px; color:var(--text-muted); margin-top:4px; }
.st-toggle { display:flex; background:var(--surface); border-radius:6px; padding:2px; gap:2px; flex:0 0 auto; }
.st-seg { font-size:12px; padding:5px 12px; border-radius:5px; color:var(--text-muted); cursor:pointer; }
.st-seg.active { background:var(--bg); color:var(--text); font-weight:500; }
.st-summary { display:flex; align-items:center; gap:24px; padding:14px 0; border-top:1px solid var(--border);
  border-bottom:1px solid var(--border); margin-bottom:20px; flex-wrap:wrap; }
.st-metric { display:flex; flex-direction:column; gap:2px; }
.st-metric-val { font-size:24px; font-weight:700; line-height:1; color:var(--text); }
.st-metric-sub { font-size:11.5px; color:var(--text-muted); }
.st-vsep { width:1px; height:34px; background:var(--border); }
.st-section { margin-bottom:24px; align-items:stretch; }
.st-label { font-size:10px; text-transform:uppercase; letter-spacing:.04em; color:var(--text-dim); font-weight:600; margin-bottom:10px; }
.st-college-row { display:flex; align-items:center; gap:12px; height:32px; }
.st-college-name { flex:0 0 150px; font-size:12.5px; color:var(--text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.st-college-bar-track { flex:1 1 auto; height:8px; border-radius:3px; background:var(--surface-hover); overflow:hidden; }
.st-college-bar-fill { height:100%; border-radius:3px; background:var(--accent); }
.st-college-time { flex:0 0 56px; text-align:right; font-family:var(--font-mono); font-size:12px; color:var(--text-muted); }
.st-day-head { display:flex; align-items:center; gap:12px; margin:14px 0 4px; }
.st-day-label { font-size:10px; text-transform:uppercase; letter-spacing:.04em; color:var(--text-dim); font-weight:600; }
.st-day-rule { flex:1; height:1px; background:var(--border); }
.st-activity-row { display:flex; align-items:center; gap:12px; min-height:40px; padding:4px 0; }
.st-act-date { font-family:var(--font-mono); font-size:11px; color:var(--text-dim); flex:0 0 46px; }
.st-act-badge { font-family:var(--font-mono); font-size:10px; color:var(--text-muted); border:1px solid var(--border);
  border-radius:4px; padding:2px 6px; flex:0 0 auto; white-space:nowrap; }
.st-act-main { flex:1 1 auto; min-width:0; }
.st-act-title { font-size:12.5px; color:var(--text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.st-act-meta { font-size:11px; color:var(--text-dim); margin-top:1px; }
.st-act-dur { font-family:var(--font-mono); font-size:11.5px; color:var(--text-muted); flex:0 0 auto; text-align:right; }
.st-empty { padding:24px 10px; text-align:center; color:var(--text-dim); font-size:13px; }
"""


def _course_college_map() -> dict[str, str]:
    return {c.id: c.college[0] for c in data_store.cours if c.college}


def render_stats_cockpit() -> None:
    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)

    state = {"days": 7}

    with ui.column().classes("st-wrap gap-0"):
        topbar = ui.element("div").classes("st-topbar")
        summary = ui.element("div").classes("st-summary")
        college_section = ui.column().classes("w-full st-section")
        activity_section = ui.column().classes("w-full st-section")

    def _select_days(days: int) -> None:
        state["days"] = days
        _render()

    def _draw_topbar() -> None:
        topbar.clear()
        with topbar:
            with ui.column().classes("gap-0"):
                ui.label("Statistiques").classes("st-title")
                ui.label("Activité, temps et maîtrise").classes("st-subtitle")
            with ui.element("div").classes("st-toggle"):
                for label, value in [("7 j", 7), ("30 j", 30), ("Tout", 0)]:
                    seg = ui.element("div").classes(
                        "st-seg active" if state["days"] == value else "st-seg")
                    with seg:
                        ui.label(label)
                    seg.on("click", lambda v=value: _select_days(v))

    def _draw_summary(kpis: dict) -> None:
        summary.clear()
        period_lbl = f"{state['days']} j" if state["days"] else "tout"
        avg = kpis["avg_score"]
        avg_color = _LEVEL_COLOR.get(_level_from_score(avg), "var(--text-muted)") if avg is not None else "var(--text-dim)"

        with summary:
            with ui.element("div").classes("st-metric"):
                ui.label(_fmt_minutes(kpis["total_minutes"])).classes("st-metric-val")
                ui.label(f"temps travaillé · {period_lbl}").classes("st-metric-sub")

            ui.element("div").classes("st-vsep")

            with ui.element("div").classes("st-metric"):
                ui.label(str(kpis["session_count"])).classes("st-metric-val")
                ui.label("révisions faites").classes("st-metric-sub")

            ui.element("div").classes("st-vsep")

            with ui.element("div").classes("st-metric"):
                ui.label(f"{avg}%" if avg is not None else "—").classes("st-metric-val").style(f"color:{avg_color}")
                ui.label(f"maîtrise moyenne · {kpis['tracked_count']} cours").classes("st-metric-sub")

    def _draw_college_time(sessions: list) -> None:
        college_section.clear()
        college_map = _course_college_map()
        totals: dict[str, int] = {}
        for s in sessions:
            cid = _get(s, "course_id")
            college = college_map.get(cid)
            if not college:
                continue
            totals[college] = totals.get(college, 0) + (_get(s, "duration_minutes", 0) or 0)

        with college_section:
            ui.label("TEMPS PAR COLLÈGE").classes("st-label")
            if not totals:
                with ui.element("div").classes("st-empty"):
                    ui.label("Aucune séance rattachée à un collège sur cette période.")
                return
            ranked = sorted(totals.items(), key=lambda kv: -kv[1])
            max_min = ranked[0][1] or 1
            for college, minutes in ranked:
                with ui.element("div").classes("st-college-row"):
                    ui.label(college).classes("st-college-name")
                    with ui.element("div").classes("st-college-bar-track"):
                        ui.element("div").classes("st-college-bar-fill").style(
                            f"width:{int(minutes / max_min * 100)}%")
                    ui.label(_fmt_minutes(minutes)).classes("st-college-time")

    def _draw_activity(sessions: list) -> None:
        activity_section.clear()
        with activity_section:
            ui.label("ACTIVITÉ RÉCENTE").classes("st-label")
            if not sessions:
                with ui.element("div").classes("st-empty"):
                    ui.label("Aucune activité enregistrée.")
                return

            groups: dict[str, list] = {}
            for s in sessions:
                d = _get(s, "session_date")
                if d:
                    groups.setdefault(d, []).append(s)

            for date_str in sorted(groups.keys(), reverse=True):
                try:
                    day_lbl = _day_label(datetime.date.fromisoformat(date_str))
                except ValueError:
                    day_lbl = date_str
                with ui.element("div").classes("st-day-head"):
                    ui.label(day_lbl).classes("st-day-label")
                    ui.element("div").classes("st-day-rule")

                for s in groups[date_str]:
                    _draw_activity_row(s)

    def _draw_activity_row(s) -> None:
        item_txt = f"ITEM {_get(s, 'item_number')} – " if _get(s, "item_number") else ""
        title = f"{item_txt}{_get(s, 'course_title') or _get(s, 'course_id', '—')}"
        acts_raw = _get(s, "activity_types")
        badge = _fmt_activities(acts_raw)
        dur = _get(s, "duration_minutes")
        conf = _get(s, "confidence")
        qcm = (_get(s, "qcm_result") or "").strip().lower()

        meta_parts = []
        if conf:
            meta_parts.append(f"conf. {conf}/5")
        if qcm:
            meta_parts.append(f"QCM {qcm}")

        with ui.element("div").classes("st-activity-row"):
            d = _get(s, "session_date", "")
            ui.label(d[8:10] + "/" + d[5:7] if len(d) >= 10 else "—").classes("st-act-date")
            ui.label(badge).classes("st-act-badge")
            with ui.element("div").classes("st-act-main"):
                ui.label(title).classes("st-act-title")
                if meta_parts:
                    ui.label(" · ".join(meta_parts)).classes("st-act-meta")
            ui.label(_fmt_minutes(dur) if dur else "—").classes("st-act-dur")

    def _render() -> None:
        days = state["days"]
        snapshots = _get_all_mastery_snapshots()
        kpis = _compute_kpis(days, snapshots)

        sessions = list(local_store.get_recent_study_sessions(limit=300))
        if days > 0:
            cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
            sessions = [s for s in sessions if (_get(s, "session_date") or "") >= cutoff]

        _draw_topbar()
        _draw_summary(kpis)
        _draw_college_time(sessions)
        _draw_activity(sessions)

    _render()
