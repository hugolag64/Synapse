"""
_banner.py — Context strip (date + stats pills) + badges secondaires.
"""
from __future__ import annotations

import datetime

from nicegui import ui

from backend.core.externat.service import externat_service
from backend.state.store import data_store

from ._state import DashboardState


def render_banner(state: DashboardState) -> None:
    """Render la bande supérieure : date large + sous-titre contextuel + pills discrètes."""
    days_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    months_fr = [
        "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
        "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
    ]
    now = datetime.datetime.now()
    date_str = f"{days_fr[now.weekday()]} {now.day} {months_fr[now.month - 1]}"

    with ui.element("div").classes("w-full flex flex-col gap-2"):

        # ── Titre + pills contextuelles ───────────────────────────────────────
        with ui.element("div").classes("flex items-start justify-between gap-4"):

            # Gauche : date grande + sous-titre concis
            with ui.column().classes("gap-0.5 min-w-0"):
                ui.label(date_str).classes(
                    "synapse-display text-[32px] font-extrabold "
                    "text-slate-900 dark:text-slate-50 tracking-tight capitalize leading-none"
                )
                state.smart_lbl = ui.label("").classes(
                    "text-[15px] text-slate-500 dark:text-slate-400 font-medium mt-1"
                )

            # Droite : pills discrètes (faites, objectif, stage)
            with ui.row().classes("items-center gap-2 flex-wrap shrink-0 pt-1"):

                # Faites aujourd'hui
                state.banner_refs["done_el"] = ui.element("div").classes(
                    "flex items-center gap-1.5 px-2.5 py-1 rounded-full "
                    "bg-emerald-50 dark:bg-emerald-900/20"
                )
                with state.banner_refs["done_el"]:
                    ui.icon("check_circle", size="xs").classes("text-emerald-500")
                    state.banner_refs["done"] = ui.label("").classes(
                        "text-[12px] font-semibold text-emerald-700 dark:text-emerald-400"
                    )
                state.banner_refs["done_el"].set_visibility(False)

                # Objectif quotidien
                state.banner_refs["goal_el"] = ui.element("div").classes(
                    "flex items-center gap-1.5 px-2.5 py-1 rounded-full "
                    "bg-violet-50 dark:bg-violet-900/20 cursor-pointer"
                ).on("click", lambda: ui.navigate.to("/settings"))
                with state.banner_refs["goal_el"]:
                    ui.icon("flag", size="xs").classes("text-violet-500")
                    state.banner_refs["goal"] = ui.label("").classes(
                        "text-[12px] font-semibold text-violet-700 dark:text-violet-400"
                    )
                state.banner_refs["goal_el"].set_visibility(False)

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

                # Stage actif
                _active_stage = externat_service.get_active_stage()
                if _active_stage:
                    with ui.element("div").classes(
                        "flex items-center gap-1.5 px-2.5 py-1 rounded-full "
                        "bg-emerald-50 dark:bg-emerald-900/20 cursor-pointer"
                    ).on("click", lambda: ui.navigate.to("/externat")):
                        ui.icon("local_hospital", size="xs").classes("text-emerald-500")
                        _stage_label = f"Externat · {_active_stage.specialty}"
                        if _active_stage.days_remaining <= 7:
                            _stage_label += f" ({_active_stage.days_remaining}j)"
                        ui.label(_stage_label).classes(
                            "text-[12px] font-semibold text-emerald-700 dark:text-emerald-400"
                        ).tooltip(
                            f"Stage en cours · {_active_stage.days_elapsed}j écoulés · "
                            f"{_active_stage.days_remaining}j restants\n"
                            f"↑ Les cours de {_active_stage.specialty} sont remontés en priorité."
                        )

        # ── Barre de progression quotidienne ──────────────────────────────────
        with ui.element("div").classes("synapse-daily-bar") as _bar_el:
            state.banner_refs["daily_bar_fill"] = ui.element("div").classes(
                "synapse-daily-bar-fill"
            ).style("width:0%")
        state.banner_refs["daily_bar"] = _bar_el
        _bar_el.set_visibility(False)


def update_banner(state: DashboardState, load: dict, done_today: int = 0, week_count: int = 0, overflow_count: int = 0) -> None:
    """Met à jour la bannière Morning Brief : sous-titre concis + pills discrètes."""
    n_u = load["urgent_count"]
    n_t = load["today_count"]

    # Sous-titre : une seule ligne claire
    if n_u == 0 and n_t == 0:
        _smart_msg = "Rien à faire aujourd'hui ✓"
    elif n_u == 0:
        _smart_msg = f"{n_t} révision{'s' if n_t > 1 else ''} prévue{'s' if n_t > 1 else ''} aujourd'hui"
    elif done_today > 0 and n_u > 0 and n_t > 0:
        _smart_msg = (
            f"{done_today} faite{'s' if done_today > 1 else ''} · "
            f"{n_u} en retard · {n_t} prévue{'s' if n_t > 1 else ''}"
        )
    elif done_today > 0 and n_u > 0:
        _smart_msg = f"{done_today} faite{'s' if done_today > 1 else ''} · {n_u} en retard"
    elif n_u > 0 and n_t > 0:
        _smart_msg = f"{n_u} en retard · {n_t} prévue{'s' if n_t > 1 else ''} aujourd'hui"
    else:
        _smart_msg = f"{n_u} en retard"
    state.smart_lbl.set_text(_smart_msg)

    # Faites aujourd'hui
    state.banner_refs["done_el"].set_visibility(done_today > 0)
    if done_today > 0:
        state.banner_refs["done"].set_text(f"{done_today} faite{'s' if done_today > 1 else ''}")

    # Objectif quotidien + barre de progression
    _daily_goal = data_store.preferences.get("daily_goal", 0)
    if _daily_goal and _daily_goal > 0:
        state.banner_refs["goal_el"].set_visibility(True)
        _goal_done = done_today >= _daily_goal
        state.banner_refs["goal"].set_text(
            f"{'✓ ' if _goal_done else ''}{done_today}/{_daily_goal}"
        )
        state.banner_refs["goal_el"].classes(
            remove="bg-violet-50 dark:bg-violet-900/20 bg-green-50 dark:bg-green-900/20"
        )
        state.banner_refs["goal_el"].classes(
            add="bg-green-50 dark:bg-green-900/20" if _goal_done else "bg-violet-50 dark:bg-violet-900/20"
        )
        state.banner_refs["goal"].classes(
            remove="text-violet-700 dark:text-violet-400 text-green-700 dark:text-green-400"
        )
        state.banner_refs["goal"].classes(
            add="text-green-700 dark:text-green-400" if _goal_done else "text-violet-700 dark:text-violet-400"
        )
        _pct = min(100, int(done_today / _daily_goal * 100))
        state.banner_refs["daily_bar"].set_visibility(True)
        _fill = state.banner_refs["daily_bar_fill"]
        _fill.style(f"width:{_pct}%")
        if _goal_done:
            _fill.classes(add="complete")
        else:
            _fill.classes(remove="complete")
    else:
        state.banner_refs["goal_el"].set_visibility(False)
        state.banner_refs["daily_bar"].set_visibility(False)

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
