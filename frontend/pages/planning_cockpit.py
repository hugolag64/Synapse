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
from zoneinfo import ZoneInfo

from nicegui import ui

from backend.core.planning.service import planning_service
from backend.core.planning.policy import (
    capacity_from_preferences,
    capacity_hours_to_minutes,
    effective_capacity_minutes,
    is_vacation_day,
    return_diagnostic_tasks,
    target_for_day,
    vacation_for_preferences,
    vacation_is_expired,
    vacation_payload,
)
from backend.core.planning.focus import build_focus_rows, focus_row_label
from backend.core.planning.calendar_actions import event_duration_minutes
from backend.core.reviews.service import review_service
from backend.core.reviews.local_store import (
    create_manual_planning_entry,
    get_all_history,
    get_all_weak_points_table,
    get_manual_planning_entries,
)
from frontend.components.item_search_palette import search_items
from backend.core.google.calendar_service import calendar_service
from backend.state.store import data_store

_PLANNING_TZ = ZoneInfo("Indian/Reunion")

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
.pl-block-title { overflow:hidden; display:-webkit-box; -webkit-box-orient:vertical; }
.pl-grid[data-days="7"] .pl-block-title { -webkit-line-clamp:2; }
.pl-grid[data-days="3"] .pl-block-title { -webkit-line-clamp:3; }
.pl-grid[data-days="1"] .pl-block-title { white-space:normal; }
.pl-block { transition:background .14s ease, transform .14s ease; }
.pl-block:hover { background:var(--surface); transform:translateY(-1px); }
.pl-focus { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:8px; margin-top:18px; }
.pl-focus-row { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:11px 12px;
  border:1px solid var(--border); border-radius:8px; background:var(--surface); cursor:pointer;
  transition:background .14s ease, border-color .14s ease, transform .14s ease; }
.pl-focus-row:hover { background:var(--bg); border-color:var(--accent); transform:translateY(-1px); }
.pl-focus-label { font-size:11px; color:var(--text); }
.pl-focus-action { font-size:10px; color:var(--accent); white-space:nowrap; }
@media (max-width: 820px) { .pl-focus { grid-template-columns:1fr; } }
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
@media (max-width: 600px) { .pl-topbar { gap:10px; } }
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


def _capacity_label(minutes: int) -> str:
    hours = int(minutes) // 60
    return f"{hours} h"


def _parse_ui_date(value: object) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _vacation_label(vacation: dict) -> str:
    if not vacation.get("enabled"):
        return ""
    end = vacation.get("end_date", "")
    return "diagnostic au retour" if vacation.get("strategy") == "diagnostic_only" else f"charge réduite jusqu’au {end}"


async def render_planning_cockpit() -> None:
    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)

    state = {"anchor": datetime.date.today(), "days": 7}
    day_refs: list[dict] = []
    _manual_entries_by_day: dict[str, list[dict]] = {}

    with ui.column().classes("pl-wrap gap-0"):
        topbar = ui.element("div").classes("pl-topbar")
        return_notice = ui.element("div").classes("mb-4")
        grid = ui.element("div").classes("pl-grid")
        with ui.element("div").classes("pl-legend"):
            with ui.element("div").classes("pl-legend-item"):
                ui.element("div").classes("pl-legend-line")
                ui.label("Tâche Synapse")
            with ui.element("div").classes("pl-legend-item"):
                ui.element("div").classes("pl-legend-line event")
                ui.label("Événement calendrier")
        focus_block = ui.element("div").classes("pl-focus")


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
        prefs = data_store.preferences
        current_minutes = capacity_from_preferences(prefs)
        current_hours = current_minutes // 60
        current_vacation = vacation_for_preferences(prefs)
        selected_duration = {"value": 3}
        today_iso = datetime.date.today().isoformat()
        initial_start = current_vacation.get("start_date", today_iso)
        initial_end = current_vacation.get(
            "end_date", (datetime.date.today() + datetime.timedelta(days=2)).isoformat()
        )
        with ui.dialog() as dialog:
            with ui.card().classes("w-full max-w-sm p-4 gap-0"):
                ui.label("Ma charge").classes("text-base font-semibold")
                ui.label("Ton rythme quotidien et tes périodes de vacances.").classes(
                    "text-xs text-slate-500 mt-1"
                )
                ui.label("Capacité quotidienne").classes("text-xs font-semibold mt-5")
                capacity = ui.toggle(
                    {3: "3 h", 6: "6 h", 9: "9 h", 12: "12 h"}, value=current_hours
                ).props("dense unelevated no-caps").classes("w-full mt-2")
                custom = ui.number(
                    "Autre capacité (h)", value=current_hours, min=3, max=12, step=1
                ).props("outlined dense").classes("w-full mt-2")
                custom.set_visibility(current_hours not in {3, 6, 9, 12})
                with ui.row().classes("w-full justify-end mt-1"):
                    custom_btn = ui.button(
                        "Autre…", on_click=lambda: custom.set_visibility(True)
                    ).props("flat dense no-caps color=slate")

                enabled = ui.switch("Mode vacances", value=bool(current_vacation.get("enabled"))).classes("mt-4")
                strategy = ui.toggle(
                    {"reduced": "Charge réduite", "diagnostic_only": "Coupure complète"},
                    value=current_vacation.get("strategy", "reduced"),
                ).props("dense unelevated no-caps").classes("w-full mt-3")
                strategy.set_visibility(bool(current_vacation.get("enabled")))

                with ui.row().classes("gap-2 mt-3") as vacation_presets:
                    ui.label("Durée").classes("text-xs font-semibold self-center")
                    for days, label in ((1, "1 jour"), (3, "3 jours"), (5, "5 jours")):
                        def _select_duration(days=days) -> None:
                            selected_duration["value"] = days
                            start = _parse_ui_date(initial_start) or datetime.date.today()
                            date_range.set_value({
                                "from": start.isoformat(),
                                "to": (start + datetime.timedelta(days=days - 1)).isoformat(),
                            })

                        ui.button(label, on_click=_select_duration).props("outline dense no-caps")

                with ui.row().classes("w-full justify-end mt-1"):
                    dates_trigger = ui.button("Dates personnalisées", on_click=lambda: custom_dates.set_visibility(True)).props(
                        "flat dense no-caps color=slate"
                    )
                with ui.column().classes("w-full gap-2 mt-1") as custom_dates:
                    date_range = ui.date(
                        value={"from": initial_start, "to": initial_end}
                    ).props("outlined dense range")
                custom_dates.set_visibility(False)
                vacation_presets.set_visibility(bool(current_vacation.get("enabled")))

                def _toggle_vacation(e) -> None:
                    active = bool(e.value)
                    strategy.set_visibility(active)
                    vacation_presets.set_visibility(active)
                    custom_dates.set_visibility(False)

                enabled.on_value_change(_toggle_vacation)

                with ui.row().classes("w-full justify-end gap-2 mt-5"):
                    ui.button("Annuler", on_click=dialog.close).props("flat no-caps color=slate")

                    def _save_capacity() -> None:
                        hours = int(custom.value or capacity.value or current_hours)
                        range_value = date_range.value if isinstance(date_range.value, dict) else {}
                        start = _parse_ui_date(range_value.get("from")) or datetime.date.today()
                        end = _parse_ui_date(range_value.get("to")) or start
                        end = max(start, end)
                        vacation = {"enabled": False}
                        if enabled.value:
                            vacation = {
                                **vacation_payload(start, max(1, (end - start).days + 1), strategy.value),
                                "end_date": end.isoformat(),
                            }
                        data_store.set_preference("planning_capacity_minutes", capacity_hours_to_minutes(hours))
                        data_store.set_preference("planning_vacation", vacation)
                        dialog.close()
                        asyncio.create_task(_load_and_render())
                        ui.notify("Ma charge a été enregistrée", type="positive")

                    ui.button("Enregistrer", on_click=_save_capacity).props("unelevated color=indigo no-caps")
        dialog.open()

    def _draw_topbar(week: list[datetime.date], total_min: int | None, free_days: int | None) -> None:
        topbar.clear()
        with topbar:
            with ui.column().classes("gap-0"):
                ui.label("Planning").classes("pl-title")
                if total_min is None:
                    ui.label(f"Semaine du {_month_day(week[0])} · chargement…").classes("pl-subtitle")
                else:
                    subtitle = (
                        f"Semaine du {_month_day(week[0])} · "
                        f"charge restante {_load_label(total_min)} · "
                        f"{free_days} créneau{'x' if free_days != 1 else ''} libre{'s' if free_days != 1 else ''}"
                    )
                    vacation = vacation_for_preferences(data_store.preferences)
                    if vacation.get("enabled") and not vacation_is_expired(vacation, datetime.date.today()):
                        subtitle += f" · vacances · {_vacation_label(vacation)}"
                    ui.label(subtitle).classes("pl-subtitle")
            with ui.element("div").classes("pl-nav"):
                ui.button("Ma charge", on_click=_open_capacity_dialog).props(
                    "outline dense no-caps"
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

    def _draw_return_notice(all_tasks: list) -> None:
        return_notice.clear()
        vacation = vacation_for_preferences(data_store.preferences)
        diagnostic = return_diagnostic_tasks(all_tasks, vacation, datetime.date.today())
        if not diagnostic:
            return
        with return_notice:
            with ui.element("div").classes(
                "rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm text-indigo-900"
            ):
                ui.label("État des lieux après vacances").classes("font-semibold")
                ui.label(
                    f"{len(diagnostic)} connaissance{'s' if len(diagnostic) != 1 else ''} à tester depuis la période de coupure."
                ).classes("text-xs mt-1")

    def _focus_action(kind: str) -> None:
        if kind == "overdue":
            ui.navigate.to("/todo")
            return
        if kind == "next_session":
            target = next((d for d in _week_dates() if _target_for(d)), _week_dates()[0])
        else:
            target = next((d for d in _week_dates() if d != datetime.date.today()), _week_dates()[0])
        _open_day_actions(target)


    def _draw_focus(plans: list, all_tasks: list) -> None:
        focus_block.clear()
        rows = build_focus_rows(plans, all_tasks)
        with focus_block:
            for row in rows:
                element = ui.element("div").classes("pl-focus-row")
                element.on("click", lambda kind=row["kind"]: _focus_action(kind))
                with element:
                    ui.label(focus_row_label(row)).classes("pl-focus-label")
                    ui.label("Voir" if row["kind"] == "overdue" else "Planifier").classes("pl-focus-action")

    def _draw_skeleton(week: list[datetime.date]) -> None:
        grid.clear()
        day_refs.clear()
        today = datetime.date.today()
        with grid:
            grid.props(f'data-days="{state["days"]}"')
            grid.style(
                f"grid-template-columns:repeat({len(week)}, minmax(0,1fr));"
                f"max-width:{'100%' if len(week) == 7 else '960px'};margin:0 auto;"
            )
            for d in week:
                is_today = d == today
                card = ui.element("div").classes("pl-day today" if is_today else "pl-day")
                with card:
                    head = ui.element("div").classes("pl-day-head cursor-pointer")
                    head.on("click", lambda day=d: _open_day_actions(day))
                    with head:
                        ui.label(_DAYS_ABBR[d.weekday()]).classes("pl-day-dow")
                        ui.label(str(d.day)).classes("pl-day-date")
                        ui.icon("add", size="xs").classes("float-right text-slate-400")
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
            manual_entries = _manual_entries_by_day.get(d.isoformat(), [])
            if not plan.slots and not events and not manual_entries:
                ui.label("Rien de prévu").classes("pl-day-empty")
            for slot in plan.slots:
                with ui.element("div").classes("pl-block pl-block-task").tooltip(slot.label):
                    ui.label(slot.label).classes("pl-block-title")
                    if slot.subtitle:
                        ui.label(f"{slot.subtitle} · {slot.duration_min} min").classes("pl-block-sub")
            for entry in manual_entries:
                with ui.element("div").classes("pl-block pl-block-task"):
                    title = f"{entry['course_title']} · {entry['activity_type']}"
                    ui.label(title).classes("pl-block-title")
                    ui.label(f"Planifié manuellement · {entry['duration_minutes']} min").classes("pl-block-sub")
            for ev in events:
                summary = ev.get("summary") or "Événement"
                dur = _event_duration_min(ev)
                with ui.element("div").classes("pl-block pl-block-event").tooltip(summary):
                    ui.label(summary).classes("pl-block-title")
                    if dur:
                        h, m = divmod(dur, 60)
                        ui.label(f"{h}h{m:02d}" if h else f"{dur} min").classes("pl-block-sub")
        manual_total = sum(entry["duration_minutes"] for entry in _manual_entries_by_day.get(d.isoformat(), []))
        ref["foot"].set_text(_load_label(plan.total_min + manual_total))

    def _open_day_actions(day: datetime.date) -> None:
        with ui.dialog() as dialog:
            with ui.card().classes("w-full max-w-sm p-5"):
                ui.label(f"{_DAYS_ABBR[day.weekday()]} {day.day} {_MONTHS_FR[day.month - 1]}").classes(
                    "text-base font-semibold"
                )
                ui.label("Que veux-tu ajouter ?").classes("text-xs text-slate-500 mt-1")
                with ui.column().classes("w-full gap-2 mt-5"):
                    ui.button(
                        "Planifier un item Synapse",
                        icon="school",
                        on_click=lambda: (_close_and_open(dialog, _open_manual_item_form, day)),
                    ).props("outline no-caps unelevated").classes("w-full justify-start")
                    ui.button(
                        "Créer un événement Google Calendar",
                        icon="event",
                        on_click=lambda: (_close_and_open(dialog, _open_calendar_event_form, day)),
                    ).props("outline no-caps unelevated").classes("w-full justify-start")
                ui.button("Annuler", on_click=dialog.close).props("flat no-caps color=slate").classes("mt-3")
        dialog.open()

    def _close_and_open(dialog, callback, day: datetime.date) -> None:
        dialog.close()
        callback(day)

    def _open_manual_item_form(day: datetime.date) -> None:
        state = {"query": "", "results": [], "selected": None}
        with ui.dialog() as dialog:
            with ui.card().classes("w-full max-w-lg p-0 overflow-hidden"):
                with ui.row().classes("w-full items-center justify-between px-5 py-4 border-b"):
                    ui.label("Planifier un item Synapse").classes("text-base font-semibold")
                    ui.button(icon="close", on_click=dialog.close).props("flat round dense color=grey")
                with ui.column().classes("w-full p-5 gap-3"):
                    ui.label(f"Le {day.day} {_MONTHS_FR[day.month - 1]}").classes("text-xs text-slate-500")
                    search = ui.input(placeholder="Rechercher un numéro ou un titre…").props(
                        "outlined dense autofocus"
                    ).classes("w-full")
                    results = ui.column().classes("w-full gap-1 max-h-48 overflow-y-auto")
                    selected_label = ui.label("Aucun item sélectionné").classes("text-xs text-slate-500")
                    activity = ui.select(
                        {"revision": "Révision", "lecture": "Lecture", "qcm": "QCM", "lacune": "Lacune"},
                        value="revision", label="Activité",
                    ).props("outlined dense").classes("w-full")
                    durations = planning_service.get_durations()
                    duration = ui.number(
                        "Durée (min)", value=durations.get("revision", 20), min=5, max=240, step=5
                    ).props("outlined dense").classes("w-full")
                    add_calendar = ui.switch("Ajouter aussi à Google Calendar").props("dense")
                    with ui.row().classes("w-full justify-end gap-2 mt-2"):
                        ui.button("Annuler", on_click=dialog.close).props("flat no-caps color=slate")

                        async def _save() -> None:
                            selected = state["selected"]
                            if selected is None:
                                ui.notify("Sélectionne un item.", type="warning")
                                return
                            try:
                                entry = create_manual_planning_entry(
                                    day,
                                    selected.id,
                                    selected.title,
                                    selected.display_item_number or selected.item_number or "",
                                    activity.value,
                                    int(duration.value or 0),
                                )
                                if add_calendar.value:
                                    await _create_calendar_event_for_entry(day, entry)
                            except Exception as exc:
                                ui.notify(f"Impossible d’enregistrer : {exc}", type="negative")
                                return
                            dialog.close()
                            asyncio.create_task(_load_and_render())
                            ui.notify("Item ajouté à la journée", type="positive")

                        ui.button("Ajouter", on_click=_save).props("unelevated color=indigo no-caps")

        def _render_results() -> None:
            results.clear()
            state["results"] = search_items(state["query"], data_store.cours)
            with results:
                for course in state["results"]:
                    row = ui.element("div").classes(
                        "w-full px-3 py-2 rounded cursor-pointer hover:bg-slate-50"
                    )
                    row.on("click", lambda c=course: _select_course(c))
                    with row:
                        ui.label(f"ITEM {course.display_item_number or course.item_number or '—'} · {course.title}").classes(
                            "text-xs font-semibold"
                        )
                        ui.label(" · ".join(course.college or [])).classes("text-[11px] text-slate-400")

        def _select_course(course) -> None:
            state["selected"] = course
            selected_label.set_text(f"Sélectionné : ITEM {course.display_item_number or course.item_number or '—'} · {course.title}")

        search.on_value_change(lambda event: (state.update(query=event.value or ""), _render_results()))
        _render_results()
        dialog.open()

    def _default_event_start(day: datetime.date) -> datetime.datetime:
        now = datetime.datetime.now(_PLANNING_TZ)
        if day != now.date():
            return datetime.datetime.combine(day, datetime.time(9, 0), tzinfo=_PLANNING_TZ)
        return (now + datetime.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

    async def _create_calendar_event(
        summary: str,
        start_time: datetime.datetime,
        end_time: datetime.datetime,
        description: str = "",
    ) -> bool:
        try:
            duration = event_duration_minutes(start_time, end_time)
            result = await calendar_service.create_event(
                summary,
                start_time.isoformat(),
                duration_minutes=duration,
                description=description,
            )
        except Exception as exc:
            ui.notify(f"Impossible de créer l’événement : {exc}", type="negative")
            return False
        if not result:
            ui.notify("Google Calendar n’a pas pu créer l’événement.", type="negative")
            return False
        return True

    async def _create_calendar_event_for_entry(day: datetime.date, entry: dict) -> bool:
        start = _default_event_start(day)
        end = start + datetime.timedelta(minutes=int(entry["duration_minutes"]))
        item_number = entry.get("item_number", "")
        prefix = f"ITEM {item_number} – " if item_number else ""
        return await _create_calendar_event(
            f"{prefix}{entry['course_title']}",
            start,
            end,
            f"Planification manuelle Synapse · {entry['activity_type']}",
        )

    def _open_calendar_event_form(day: datetime.date) -> None:
        default_start = _default_event_start(day)
        default_end = default_start + datetime.timedelta(hours=1)
        with ui.dialog() as dialog:
            with ui.card().classes("w-full max-w-md p-0 overflow-hidden"):
                with ui.row().classes("w-full items-center justify-between px-5 py-4 border-b"):
                    ui.label("Créer un événement").classes("text-base font-semibold")
                    ui.button(icon="close", on_click=dialog.close).props("flat round dense color=grey")
                with ui.column().classes("w-full p-5 gap-3"):
                    ui.label(f"Le {day.day} {_MONTHS_FR[day.month - 1]}").classes("text-xs text-slate-500")
                    title = ui.input("Titre", placeholder="Ex. Sport, rendez-vous…").props("outlined dense autofocus").classes("w-full")
                    start = ui.input("Début", value=default_start.strftime("%H:%M")).props("outlined dense type=time").classes("w-full")
                    end = ui.input("Fin", value=default_end.strftime("%H:%M")).props("outlined dense type=time").classes("w-full")
                    description = ui.textarea("Description (facultatif)").props("outlined dense rows=2").classes("w-full")
                    with ui.row().classes("w-full justify-end gap-2 mt-2"):
                        ui.button("Annuler", on_click=dialog.close).props("flat no-caps color=slate")

                        async def _save_event() -> None:
                            summary = (title.value or "").strip()
                            if not summary:
                                ui.notify("Ajoute un titre à l’événement.", type="warning")
                                return
                            try:
                                start_time = datetime.datetime.combine(
                                    day, datetime.time.fromisoformat(str(start.value)), tzinfo=_PLANNING_TZ
                                )
                                end_time = datetime.datetime.combine(
                                    day, datetime.time.fromisoformat(str(end.value)), tzinfo=_PLANNING_TZ
                                )
                            except ValueError:
                                ui.notify("Vérifie les horaires.", type="warning")
                                return
                            if await _create_calendar_event(summary, start_time, end_time, description.value or ""):
                                dialog.close()
                                asyncio.create_task(_load_and_render())
                                ui.notify("Événement ajouté à Google Calendar", type="positive")

                        ui.button("Créer", on_click=_save_event).props("unelevated color=indigo no-caps")
        dialog.open()

    async def _load_and_render() -> None:
        nonlocal _manual_entries_by_day
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
        _manual_entries_by_day = {}
        manual_entries = get_manual_planning_entries(week[0], week[-1])
        for entry in manual_entries:
            _manual_entries_by_day.setdefault(entry["entry_date"], []).append(entry)
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
            target_minutes = target_for_day(d, data_store.preferences)
            if target_minutes == 0 and is_vacation_day(d, vacation_for_preferences(data_store.preferences)):
                urgent, due, lacunes_day = [], [], []
            plan = planning_service.plan_day(
                urgent,
                due,
                lacunes_day,
                target_minutes=target_minutes,
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
        _draw_return_notice(all_tasks)
        _draw_focus(plans, all_tasks)

    asyncio.create_task(_load_and_render())
