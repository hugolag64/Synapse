"""planning_cockpit.py — Vue « Planning » cockpit (refonte, session 6).

Rendu quand preferences['ui_mode'] == 'cockpit' (early-return depuis
planning.py). Grille semaine 7 colonnes : tâches Synapse (bord plein accent)
+ événements Google Calendar réels (bord pointillé) empilés par jour, pied
= charge du jour, navigation semaine, légende. Écran purement visuel —
le README (§3) ne décrit aucune action de ligne pour cette vue (contrairement
à Révisions), donc pas de bouton/Mode Focus ici. Le chemin classic
(Journée/Semaine/Consolidation + export Calendar) reste strictement inchangé.

Écarts assumés (voir Journal du CLAUDE.md de la refonte) :
  • pas de drag SortableJS (déjà noté comme écart Quasar à part entière dans
    le README — hors périmètre d'une session) ;
  • « charge restante » = somme des total_min Synapse des 7 jours affichés ;
    « créneaux libres » = jours sans aucune tâche Synapse planifiée (pied
    « — ») — le README ne définit pas ces deux chiffres plus précisément ;
  • `plan_week` ne branche pas les événements Calendar (`calendar_busy_min`
    reste à 0 côté PlanningService) : les événements réels sont donc
    récupérés ici séparément par jour et simplement affichés à côté des
    tâches, sans recalculer le temps libre.
"""
from __future__ import annotations

import asyncio
import datetime

from nicegui import ui

from backend.core.planning.service import planning_service
from backend.core.reviews.service import review_service
from backend.core.reviews.local_store import get_all_history, get_all_weak_points_table
from backend.core.google.calendar_service import calendar_service
from backend.state.store import data_store

_DAYS_ABBR = ["LUN", "MAR", "MER", "JEU", "VEN", "SAM", "DIM"]
_MONTHS_FR = ["jan", "fév", "mar", "avr", "mai", "juin",
              "juil", "août", "sep", "oct", "nov", "déc"]

_CSS = """
.pl-wrap { max-width:none; width:100%; }
.pl-topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; padding:4px 0 18px; flex-wrap:wrap; }
.pl-title { font-size:20px; font-weight:600; color:var(--text); letter-spacing:-0.01em; }
.pl-subtitle { font-size:12.5px; color:var(--text-muted); margin-top:4px; }
.pl-nav { display:flex; align-items:center; gap:10px; }
.pl-nav-arrow { width:26px; height:26px; border-radius:6px; display:flex; align-items:center; justify-content:center;
  cursor:pointer; color:var(--text-muted); border:1px solid var(--border); background:var(--bg); font-size:14px; }
.pl-nav-arrow:hover { background:var(--surface); }
.pl-nav-range { font-family:var(--font-mono); font-size:12px; color:var(--text-muted); min-width:96px; text-align:center; }
.pl-grid { display:grid; gap:12px; width:100%; justify-content:center; }
.pl-day { border:1px solid var(--border); border-radius:8px; min-height:250px; display:flex; flex-direction:column;
  background:var(--bg); overflow:hidden; }
.pl-day.today { border-color:var(--accent); background:var(--accent-wash); }
.pl-day-head { padding:10px 10px 8px; border-bottom:1px solid var(--border); }
.pl-day.today .pl-day-head { border-bottom-color:var(--accent); }
.pl-day-dow { font-size:10px; text-transform:uppercase; letter-spacing:.04em; color:var(--text-dim); font-weight:600; }
.pl-day.today .pl-day-dow { color:var(--accent); }
.pl-day-date { font-family:var(--font-mono); font-size:11.5px; color:var(--text-muted); margin-left:5px; }
.pl-day.today .pl-day-date { color:var(--accent); font-weight:600; }
.pl-day-body { flex:1; padding:7px 7px; display:flex; flex-direction:column; gap:5px; }
.pl-block { border-radius:4px; padding:5px 6px; font-size:11px; line-height:1.3; }
.pl-block-task { border-left:3px solid var(--accent); background:var(--bg); color:var(--text); }
.pl-day.today .pl-block-task { background:var(--bg); }
.pl-block-event { border-left:3px dashed var(--text-dim); background:transparent; color:var(--text-muted); }
.pl-block-title { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.pl-block-sub { font-size:10px; color:var(--text-dim); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.pl-day-empty { padding:10px 4px; color:var(--text-dim); font-size:11px; font-style:italic; }
.pl-day-foot { padding:7px 10px; border-top:1px solid var(--border); font-family:var(--font-mono); font-size:11px;
  color:var(--text-muted); text-align:center; }
.pl-day.today .pl-day-foot { border-top-color:var(--accent); color:var(--accent); font-weight:600; }
.pl-legend { display:flex; gap:22px; margin-top:14px; flex-wrap:wrap; }
.pl-legend-item { display:flex; align-items:center; gap:7px; font-size:11.5px; color:var(--text-muted); }
.pl-legend-line { width:20px; height:0; border-top:2px solid var(--accent); }
.pl-legend-line.event { border-top:2px dashed var(--text-dim); }
.pl-view { display:flex; align-items:center; gap:2px; border:1px solid var(--border); border-radius:7px; padding:2px; }
.pl-view-btn { border:0; background:transparent; color:var(--text-muted); border-radius:5px; padding:5px 9px; font-size:11px; cursor:pointer; }
.pl-view-btn:hover { background:var(--surface); }
.pl-view-btn.active { color:var(--accent); background:var(--accent-wash); font-weight:600; }
.pl-bottom { display:grid; grid-template-columns:minmax(0,1.2fr) minmax(280px,.8fr); gap:16px; margin-top:24px; }
.pl-bottom-card { border:1px solid var(--border); border-radius:10px; background:var(--surface); padding:16px; }
.pl-bottom-title { font-size:13px; font-weight:600; color:var(--text); }
.pl-bottom-subtitle { font-size:11px; color:var(--text-muted); margin-top:3px; }
.pl-stat-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-top:14px; }
.pl-stat { padding:10px; border-radius:8px; background:var(--bg); border:1px solid var(--border); }
.pl-stat-value { font-family:var(--font-mono); font-size:17px; font-weight:600; color:var(--text); }
.pl-stat-label { font-size:10px; color:var(--text-muted); margin-top:2px; }
.pl-queue-item { display:flex; align-items:center; gap:8px; padding:9px 0; border-bottom:1px solid var(--border); }
.pl-queue-item:last-child { border-bottom:0; }
.pl-queue-title { flex:1; min-width:0; font-size:11.5px; color:var(--text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.pl-queue-meta { font-size:10px; color:var(--text-muted); white-space:nowrap; }
@media (max-width: 820px) { .pl-bottom { grid-template-columns:1fr; } }
@media (max-width: 600px) { .pl-stat-grid { grid-template-columns:1fr 1fr; } }
"""


def _month_day(d: datetime.date) -> str:
    return f"{d.day} {_MONTHS_FR[d.month - 1]}"


def _week_range_label(monday: datetime.date, sunday: datetime.date) -> str:
    if monday.month == sunday.month:
        return f"{monday.day}–{sunday.day} {_MONTHS_FR[monday.month - 1]}"
    return f"{monday.day} {_MONTHS_FR[monday.month - 1]}–{sunday.day} {_MONTHS_FR[sunday.month - 1]}"


def _load_label(total_min: int) -> str:
    if total_min <= 0:
        return "—"
    h, m = divmod(total_min, 60)
    return f"{h}h{m:02d}" if h else f"{m} min"


def _event_duration_min(ev: dict) -> int | None:
    try:
        s = ev.get("start", {}).get("dateTime")
        e = ev.get("end", {}).get("dateTime")
        if not (s and e):
            return None
        start = datetime.datetime.fromisoformat(s)
        end = datetime.datetime.fromisoformat(e)
        return max(0, int((end - start).total_seconds() / 60))
    except Exception:
        return None


def _target_for(day: datetime.date) -> dict:
    targets = data_store.preferences.get("planning_targets", {})
    value = targets.get(day.isoformat(), {}) if isinstance(targets, dict) else {}
    return value if isinstance(value, dict) else {}


async def render_planning_cockpit() -> None:
    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)

    state = {"anchor": datetime.date.today(), "days": 7}
    day_refs: list[dict] = []

    with ui.column().classes("pl-wrap gap-0"):
        topbar = ui.element("div").classes("pl-topbar")
        grid = ui.element("div").classes("pl-grid")
        with ui.element("div").classes("pl-legend"):
            with ui.element("div").classes("pl-legend-item"):
                ui.element("div").classes("pl-legend-line")
                ui.label("Tâche Synapse")
            with ui.element("div").classes("pl-legend-item"):
                ui.element("div").classes("pl-legend-line event")
                ui.label("Événement calendrier")

        bottom = ui.element("div").classes("pl-bottom")

    def _week_dates() -> list[datetime.date]:
        anchor = state["anchor"]
        if state["days"] == 7:
            anchor = anchor - datetime.timedelta(days=anchor.weekday())
        return [anchor + datetime.timedelta(days=i) for i in range(state["days"])]

    def _shift_week(delta_weeks: int) -> None:
        state["anchor"] = state["anchor"] + datetime.timedelta(days=delta_weeks * state["days"])
        asyncio.create_task(_load_and_render())

    def _set_view(days: int) -> None:
        state["days"] = days
        asyncio.create_task(_load_and_render())

    def _open_capacity_dialog() -> None:
        fields: dict[str, tuple] = {}
        dates = _week_dates()
        with ui.dialog() as dialog:
            with ui.card().classes("w-full max-w-xl p-5"):
                ui.label("Définir ma charge").classes("text-lg font-semibold")
                ui.label("Choisis une durée ou un nombre d’items par jour. Les urgences restent prioritaires.").classes(
                    "text-xs text-slate-500 mt-1"
                )
                with ui.column().classes("w-full gap-2 mt-4"):
                    for day in dates:
                        target = _target_for(day)
                        with ui.row().classes("w-full items-center gap-2"):
                            ui.label(f"{_DAYS_ABBR[day.weekday()]} {day.day} {_MONTHS_FR[day.month - 1]}").classes(
                                "w-28 text-xs font-semibold"
                            )
                            mode = ui.select(
                                {"minutes": "Durée", "items": "Items"},
                                value=target.get("mode", "minutes"),
                            ).props("outlined dense").classes("w-28")
                            value = ui.number(
                                value=target.get("value", 0), min=0, step=5,
                            ).props("outlined dense").classes("w-28")
                            ui.label("min" if target.get("mode", "minutes") == "minutes" else "items").classes(
                                "text-xs text-slate-400"
                            )
                            fields[day.isoformat()] = (mode, value)

                with ui.row().classes("w-full justify-end gap-2 mt-5"):
                    ui.button("Annuler", on_click=dialog.close).props("flat color=slate")

                    def _save_capacity() -> None:
                        targets = data_store.preferences.get("planning_targets", {})
                        targets = dict(targets) if isinstance(targets, dict) else {}
                        for iso, (mode, value) in fields.items():
                            amount = int(value.value or 0)
                            if amount > 0:
                                targets[iso] = {"mode": mode.value, "value": amount}
                            else:
                                targets.pop(iso, None)
                        data_store.set_preference("planning_targets", targets)
                        dialog.close()
                        asyncio.create_task(_load_and_render())
                        ui.notify("Objectifs de charge enregistrés", type="positive")

                    ui.button("Enregistrer", on_click=_save_capacity).props("unelevated color=indigo")
        dialog.open()

    def _draw_topbar(week: list[datetime.date], total_min: int | None, free_days: int | None) -> None:
        topbar.clear()
        with topbar:
            with ui.column().classes("gap-0"):
                ui.label("Planning").classes("pl-title")
                if total_min is None:
                    ui.label(f"Semaine du {_month_day(week[0])} · chargement…").classes("pl-subtitle")
                else:
                    ui.label(
                        f"Semaine du {_month_day(week[0])} · "
                        f"charge restante {_load_label(total_min)} · "
                        f"{free_days} créneau{'x' if free_days != 1 else ''} libre{'s' if free_days != 1 else ''}"
                    ).classes("pl-subtitle")
            with ui.element("div").classes("pl-nav"):
                ui.button("Ma charge", icon="tune", on_click=_open_capacity_dialog).props(
                    "flat dense no-caps"
                )
                prev_btn = ui.element("div").classes("pl-nav-arrow")
                with prev_btn:
                    ui.label("‹")
                prev_btn.on("click", lambda: _shift_week(-1))
                range_label = _month_day(week[0]) if len(week) == 1 else _week_range_label(week[0], week[-1])
                ui.label(range_label).classes("pl-nav-range")
                next_btn = ui.element("div").classes("pl-nav-arrow")
                with next_btn:
                    ui.label("›")
                next_btn.on("click", lambda: _shift_week(1))
                with ui.element("div").classes("pl-view"):
                    for days, label in ((1, "1j"), (3, "3j"), (7, "7j")):
                        view_btn = ui.element("div").classes(
                            "pl-view-btn active" if state["days"] == days else "pl-view-btn"
                        )
                        with view_btn:
                            ui.label(label)
                        view_btn.on("click", lambda d=days: _set_view(d))

    def _draw_skeleton(week: list[datetime.date]) -> None:
        grid.clear()
        day_refs.clear()
        today = datetime.date.today()
        with grid:
            grid.style(
                f"grid-template-columns:repeat({len(week)}, minmax(0,1fr));"
                f"max-width:{'100%' if len(week) == 7 else '960px'};margin:0 auto;"
            )
            for d in week:
                is_today = d == today
                card = ui.element("div").classes("pl-day today" if is_today else "pl-day")
                with card:
                    with ui.element("div").classes("pl-day-head"):
                        ui.label(_DAYS_ABBR[d.weekday()]).classes("pl-day-dow")
                        ui.label(str(d.day)).classes("pl-day-date")
                    body = ui.column().classes("pl-day-body gap-1.5 w-full")
                    with body:
                        ui.label("Chargement…").classes("pl-day-empty")
                    foot = ui.label("").classes("pl-day-foot")
                day_refs.append({"body": body, "foot": foot})

    def _draw_day(idx: int, d: datetime.date, plan, events: list) -> None:
        ref = day_refs[idx]
        body = ref["body"]
        body.clear()
        with body:
            if not plan.slots and not events:
                ui.label("Rien de prévu").classes("pl-day-empty")
            for slot in plan.slots:
                with ui.element("div").classes("pl-block pl-block-task"):
                    ui.label(slot.label).classes("pl-block-title")
                    if slot.subtitle:
                        ui.label(f"{slot.subtitle} · {slot.duration_min} min").classes("pl-block-sub")
            for ev in events:
                summary = ev.get("summary") or "Événement"
                dur = _event_duration_min(ev)
                with ui.element("div").classes("pl-block pl-block-event"):
                    ui.label(summary).classes("pl-block-title")
                    if dur:
                        h, m = divmod(dur, 60)
                        ui.label(f"{h}h{m:02d}" if h else f"{dur} min").classes("pl-block-sub")
        ref["foot"].set_text(_load_label(plan.total_min))

    def _draw_bottom(plans: list, active_lacunes: list[dict], all_tasks: list) -> None:
        bottom.clear()
        total_min = sum(p.total_min for p in plans)
        active_days = sum(1 for p in plans if p.total_min > 0)
        overdue = sum(1 for task in all_tasks if task.days_overdue > 0)
        with bottom:
            with ui.element("div").classes("pl-bottom-card"):
                ui.label("Pilotage de la période").classes("pl-bottom-title")
                ui.label("Répartir l’effort sans surcharger une journée.").classes("pl-bottom-subtitle")
                with ui.element("div").classes("pl-stat-grid"):
                    for value, label in (
                        (_load_label(total_min), "charge planifiée"),
                        (f"{active_days}/{len(plans)}", "jours actifs"),
                        (str(overdue), "révisions en retard"),
                    ):
                        with ui.element("div").classes("pl-stat"):
                            ui.label(value).classes("pl-stat-value")
                            ui.label(label).classes("pl-stat-label")
                if plans and max(p.total_min for p in plans) > 120:
                    ui.label("Une journée dépasse 2 h : envisage de déplacer une session.").classes(
                        "pl-bottom-subtitle mt-3 text-amber-600"
                    )
                else:
                    ui.label("La charge est répartie de façon raisonnable.").classes(
                        "pl-bottom-subtitle mt-3"
                    )

            with ui.element("div").classes("pl-bottom-card"):
                ui.label("À placer").classes("pl-bottom-title")
                ui.label("Lacunes actives à intégrer dans une prochaine session.").classes(
                    "pl-bottom-subtitle"
                )
                queue = active_lacunes[:4]
                if not queue:
                    ui.label("Rien à placer pour le moment.").classes("pl-bottom-subtitle mt-4")
                for lacune in queue:
                    with ui.element("div").classes("pl-queue-item"):
                        ui.icon("flag", size="xs").classes("text-amber-500")
                        ui.label(
                            lacune.get("title") or lacune.get("description") or "Point faible"
                        ).classes("pl-queue-title")
                        ui.label("lacune").classes("pl-queue-meta")

    async def _load_and_render() -> None:
        week = _week_dates()
        _draw_topbar(week, None, None)
        _draw_skeleton(week)

        history = get_all_history()
        all_tasks = review_service.generate_reviews(context="college", history=history)
        active_lacunes_raw = get_all_weak_points_table(status_filter=None)
        active_lacunes = [
            lc for lc in active_lacunes_raw
            if (lc["status"] or "").lower() in {"active", "à revoir", "récurrente"}
        ]
        # planning_service.plan_week() ancre toujours ses 7 offsets sur
        # date.today() (jour 0 = aujourd'hui, jamais le lundi de la semaine
        # affichée) — inutilisable tel quel dès qu'on navigue vers une autre
        # semaine que celle en cours. On rappelle donc plan_day() nous-mêmes
        # par date réelle du grid, avec la même règle que plan_week (retard +
        # lacunes uniquement sur la vraie date du jour, jamais sur les autres
        # colonnes, y compris quand "aujourd'hui" n'est pas la 1re colonne).
        today = datetime.date.today()
        plans = []
        for d in week:
            if d == today:
                urgent = [t for t in all_tasks if t.days_overdue > 0]
                due = [t for t in all_tasks if t.days_overdue == 0 and t.due_date == d]
                lacunes_day = active_lacunes
            else:
                urgent = []
                due = [t for t in all_tasks if t.due_date == d]
                lacunes_day = []
            target = _target_for(d)
            plan = planning_service.plan_day(
                urgent,
                due,
                lacunes_day,
                target_minutes=target.get("value") if target.get("mode") == "minutes" else None,
                target_items=target.get("value") if target.get("mode") == "items" else None,
            )
            plan.date = d
            plans.append(plan)

        # Séquentiel, jamais en parallèle : le client Google Calendar n'est pas
        # thread-safe entre appels concurrents (cf. calendar_service.get_events_for_day
        # et todo.py::_load_week_ajoute — même contrainte déjà documentée ailleurs).
        for idx, (d, plan) in enumerate(zip(week, plans)):
            try:
                events = await calendar_service.get_events_for_day(d)
            except Exception:
                events = []
            _draw_day(idx, d, plan, events or [])

        total_min = sum(p.total_min for p in plans)
        free_days = sum(1 for p in plans if p.total_min <= 0)
        _draw_topbar(week, total_min, free_days)
        _draw_bottom(plans, active_lacunes, all_tasks)

    asyncio.create_task(_load_and_render())
