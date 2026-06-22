"""
_agenda.py — Agenda du jour + Lacune du Jour.
"""
from __future__ import annotations

import datetime

from nicegui import ui
from loguru import logger

from backend.core.reviews import local_store
from backend.core.google.calendar_service import calendar_service
from backend.state.store import data_store

from ._state import DashboardState


def render_agenda_section(state: DashboardState) -> None:
    """Render l'expansion agenda + la carte Lacune du Jour (structure fixe)."""
    agenda_open_pref = data_store.preferences.get("agenda_open", True)

    def _on_agenda_toggle(e):
        data_store.set_preference("agenda_open", e.value)

    with ui.expansion(
        value=agenda_open_pref,
        on_value_change=_on_agenda_toggle,
    ).classes(
        "w-full rounded-2xl shadow-sm border border-slate-200 dark:border-slate-800 "
        "bg-white dark:bg-slate-900"
    ) as _agenda_exp:
        with _agenda_exp.add_slot("header"):
            with ui.row().classes("items-center gap-2 px-5 py-3 w-full"):
                ui.icon("calendar_today", color="violet").classes(
                    "bg-violet-50 dark:bg-violet-900/20 p-1.5 rounded-md"
                )
                ui.label("Agenda du Jour").classes(
                    "font-semibold text-slate-800 dark:text-slate-100 text-[15px]"
                )
        with ui.column().classes("w-full gap-2 px-5 pb-4"):
            state.agenda_col = ui.column().classes("w-full gap-2")

    # PP-04 — Lacune du Jour
    try:
        _lacunes_jour = local_store.get_active_critical_weak_points(severity_threshold=3)[:2]
    except Exception:
        _lacunes_jour = []

    if _lacunes_jour:
        with ui.card().classes(
            "w-full rounded-2xl p-4 shadow-sm border border-amber-200 "
            "dark:border-amber-800 bg-amber-50 dark:bg-amber-950/30 flex flex-col gap-3"
        ):
            with ui.row().classes("items-center gap-2"):
                ui.icon("report_problem", size="sm").classes("text-amber-500")
                ui.label("Lacune du Jour").classes(
                    "text-xs font-bold uppercase tracking-wider "
                    "text-amber-700 dark:text-amber-400 flex-1"
                )
                ui.button(
                    "Tout voir",
                    on_click=lambda: ui.navigate.to("/lacunes"),
                ).props("flat dense size=xs color=amber-7").classes("text-[11px] font-semibold")

            for _lac in _lacunes_jour:
                with ui.element("div").classes(
                    "w-full rounded-xl bg-white dark:bg-slate-900 "
                    "border border-amber-100 dark:border-amber-900/50 p-3"
                ):
                    with ui.row().classes("items-start gap-2 w-full"):
                        _sev = _lac["severity"] if _lac["severity"] else 2
                        _sev_color = (
                            "text-red-500" if _sev >= 4
                            else "text-orange-500" if _sev >= 3
                            else "text-slate-400"
                        )
                        ui.label("!" * min(_sev, 3)).classes(
                            f"text-[11px] font-black shrink-0 {_sev_color}"
                        )
                        with ui.column().classes("gap-0.5 min-w-0 flex-1"):
                            _cat = _lac["category"] or ""
                            _det = _lac["detail"] or ""
                            _ctitle = _lac["course_title"] or ""
                            if _cat:
                                ui.label(_cat.capitalize()).classes(
                                    "text-[11px] font-bold text-amber-600 dark:text-amber-400"
                                )
                            ui.label(_det).classes(
                                "text-xs text-slate-700 dark:text-slate-300 leading-snug"
                            ).style(
                                "display:-webkit-box;-webkit-line-clamp:2;"
                                "-webkit-box-orient:vertical;overflow:hidden"
                            )
                            if _ctitle:
                                ui.label(_ctitle).classes("text-[11px] text-slate-400 truncate")


async def load_agenda(state: DashboardState) -> None:
    """Charge les événements calendrier et met à jour state.agenda_col."""
    try:
        events = (
            data_store.dashboard_data.get("events")
            or await calendar_service.get_events_for_day(datetime.date.today())
        )
        if state.agenda_col.is_deleted:
            return
        _render_events(state.agenda_col, events)
    except Exception as exc:
        if state.agenda_col is None or state.agenda_col.is_deleted:
            return
        logger.warning(f"Agenda load failed: {exc}")
        state.agenda_col.clear()
        with state.agenda_col:
            with ui.column().classes("w-full items-center py-4 gap-2"):
                ui.icon("cloud_off", size="sm").classes("text-slate-300 opacity-60")
                ui.label("Agenda indisponible").classes("text-xs text-slate-400 italic")
                ui.button(
                    "Réessayer",
                    on_click=lambda: ui.navigate.reload(),
                ).props("flat dense size=xs color=grey-7").classes("text-[11px] font-medium mt-1")


def _render_events(container, events: list) -> None:
    container.clear()
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    days_map = {0: "Lun", 1: "Mar", 2: "Mer", 3: "Jeu", 4: "Ven", 5: "Sam", 6: "Dim"}

    if not events:
        with container:
            with ui.column().classes("w-full items-center py-8 text-slate-400 gap-2"):
                ui.icon("event_busy", size="lg").classes("opacity-40")
                ui.label("Rien de prévu").classes("text-xs font-medium")
        return

    with container:
        for evt in events:
            start_raw = evt.get("start", {}).get("dateTime") or evt.get("start", {}).get("date", "")
            if "T" in start_raw:
                dt = datetime.datetime.fromisoformat(start_raw)
                time_str = dt.strftime("%H:%M")
                evt_date = dt.date()
            else:
                evt_date = datetime.date.fromisoformat(start_raw) if start_raw else today
                time_str = "Journée"

            if evt_date == today:
                day_lbl = "Auj."
                line_color = "bg-violet-400"
            elif evt_date == tomorrow:
                day_lbl = "Dem."
                line_color = "bg-blue-300"
            else:
                day_lbl = f"{days_map.get(evt_date.weekday(), '')} {evt_date.day}"
                line_color = "bg-slate-300"

            title = evt.get("summary", "Sans titre")
            with ui.row().classes(
                "w-full items-center gap-3 p-2 rounded-lg hover:bg-slate-50 "
                "dark:hover:bg-slate-800 transition-all"
            ):
                with ui.column().classes("items-center min-w-[2.5rem] gap-0"):
                    ui.label(day_lbl).classes("text-[11px] font-bold text-slate-400 uppercase")
                    ui.label(time_str).classes("text-xs font-bold text-slate-700 dark:text-slate-200")
                ui.element("div").classes(f"w-0.5 h-8 {line_color} rounded-full")
                ui.label(title).classes(
                    "text-xs font-medium text-slate-700 dark:text-slate-200 truncate"
                )
