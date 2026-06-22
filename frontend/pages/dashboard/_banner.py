"""
_banner.py — Context strip (date + stats pills) + badges secondaires.
"""
from __future__ import annotations

import datetime

from nicegui import ui

from backend.core.reviews import local_store
from backend.core.externat.service import externat_service
from backend.state.store import data_store

from ._state import DashboardState


def render_banner(state: DashboardState) -> None:
    """Render la bande supérieure : date, pills stats, badges secondaires."""
    days_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    months_fr = [
        "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
        "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
    ]
    now = datetime.datetime.now()
    date_str = f"{days_fr[now.weekday()]} {now.day} {months_fr[now.month - 1]}"

    with ui.element("div").classes("synapse-context-strip"):

        # ── Ligne principale : date | stats ───────────────────────────────────
        with ui.element("div").classes("synapse-context-strip-main"):

            # Gauche : date + phrase décisionnelle
            with ui.column().classes("gap-0.5 min-w-0"):
                ui.label(date_str).classes(
                    "synapse-display text-[28px] font-extrabold "
                    "text-slate-900 dark:text-slate-50 tracking-tight capitalize leading-none"
                )
                state.smart_lbl = ui.label("").classes(
                    "text-[13px] text-slate-500 dark:text-slate-400 font-medium mt-1"
                )

            # Droite : pills stats primaires
            with ui.row().classes("items-center gap-2 flex-wrap shrink-0"):

                # Urgentes
                with ui.element("div").classes(
                    "flex items-center gap-1.5 px-3 py-2 rounded-xl "
                    "bg-red-50 dark:bg-red-900/20 border border-red-100 dark:border-red-800/50"
                ):
                    ui.icon("priority_high", size="xs").classes("text-red-500")
                    state.banner_refs["urgent_n"] = ui.label("…").classes(
                        "text-[15px] font-extrabold tabular-nums leading-none "
                        "text-red-600 dark:text-red-400"
                    )
                    state.banner_refs["urgent_lbl"] = ui.label("urgente(s)").classes(
                        "text-[13px] font-semibold text-red-500"
                    )
                state.banner_refs["urgent"] = state.banner_refs["urgent_n"]

                # Aujourd'hui
                with ui.element("div").classes(
                    "flex items-center gap-1.5 px-3 py-2 rounded-xl "
                    "bg-blue-50 dark:bg-blue-900/20"
                ):
                    ui.icon("today", size="xs").classes("text-blue-500")
                    state.banner_refs["today"] = ui.label("…").classes(
                        "text-[13px] font-semibold text-blue-700 dark:text-blue-400"
                    )

                # Temps estimé
                with ui.element("div").classes(
                    "flex items-center gap-1.5 px-3 py-2 rounded-xl "
                    "bg-slate-100 dark:bg-slate-800"
                ):
                    ui.icon("schedule", size="xs").classes("text-slate-400")
                    state.banner_refs["time"] = ui.label("…").classes(
                        "text-[13px] font-semibold text-slate-600 dark:text-slate-300"
                    )

                # Stage actif
                _active_stage = externat_service.get_active_stage()
                if _active_stage:
                    with ui.element("div").classes(
                        "flex items-center gap-1.5 px-3 py-2 rounded-xl "
                        "bg-emerald-50 dark:bg-emerald-900/20 cursor-pointer"
                    ).on("click", lambda: ui.navigate.to("/externat")):
                        ui.icon("local_hospital", size="xs").classes("text-emerald-500")
                        _stage_label = f"Externat · {_active_stage.specialty}"
                        if _active_stage.days_remaining <= 7:
                            _stage_label += f" ({_active_stage.days_remaining}j)"
                        ui.label(_stage_label).classes(
                            "text-[13px] font-semibold text-emerald-700 dark:text-emerald-400"
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

        # ── Badges secondaires (inside strip) ─────────────────────────────────
        with ui.element("div").classes("synapse-context-strip-badges") as _badges_row:

            # UX-06 — Faites aujourd'hui
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

            # IP-06 — Objectif quotidien
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

            # UX-10 — Cette semaine
            state.banner_refs["week_el"] = ui.element("div").classes(
                "flex items-center gap-1.5 px-2.5 py-1 rounded-full "
                "bg-slate-100 dark:bg-slate-800"
            )
            with state.banner_refs["week_el"]:
                state.banner_refs["week"] = ui.label("").classes(
                    "text-[12px] font-semibold text-slate-500 dark:text-slate-400"
                )
            state.banner_refs["week_el"].set_visibility(False)

            # Lacunes critiques
            state.banner_refs["lacunes_el"] = ui.element("div").classes(
                "flex items-center gap-1.5 px-2.5 py-1 rounded-full "
                "bg-red-50 dark:bg-red-900/20 cursor-pointer"
            ).on("click", lambda: ui.navigate.to("/lacunes"))
            with state.banner_refs["lacunes_el"]:
                ui.icon("report_problem", size="xs").classes("text-red-500")
                state.banner_refs["lacunes"] = ui.label("").classes(
                    "text-[12px] font-semibold text-red-700 dark:text-red-400"
                )
            state.banner_refs["lacunes_el"].set_visibility(False)

            # Lacunes à revoir
            state.banner_refs["revoir_el"] = ui.element("div").classes(
                "flex items-center gap-1.5 px-2.5 py-1 rounded-full "
                "bg-amber-50 dark:bg-amber-900/20 cursor-pointer"
            ).on("click", lambda: ui.navigate.to("/lacunes"))
            with state.banner_refs["revoir_el"]:
                ui.icon("bookmark", size="xs").classes("text-amber-500")
                state.banner_refs["revoir"] = ui.label("").classes(
                    "text-[12px] font-semibold text-amber-700 dark:text-amber-400"
                )
            state.banner_refs["revoir_el"].set_visibility(False)

            # Charge lourde
            state.banner_refs["heavy"] = ui.element("div").classes(
                "flex items-center gap-1.5 px-2.5 py-1 rounded-full "
                "bg-amber-50 dark:bg-amber-900/20"
            )
            with state.banner_refs["heavy"]:
                ui.icon("warning", size="xs").classes("text-amber-500")
                ui.label("Charge lourde").classes(
                    "text-[12px] font-semibold text-amber-700 dark:text-amber-400"
                )
            state.banner_refs["heavy"].set_visibility(False)

        state.banner_refs["badges_row"] = _badges_row
        _badges_row.set_visibility(False)


def update_banner(state: DashboardState, load: dict, done_today: int = 0, week_count: int = 0) -> None:
    """Met à jour tous les éléments de la bannière."""
    n_u = load["urgent_count"]
    n_t = load["today_count"]
    state.banner_refs["urgent_n"].set_text(str(n_u))
    state.banner_refs["urgent_lbl"].set_text(
        f"urgente{'s' if n_u != 1 else ''}"
    )

    # IU-04 — Smart Banner : phrase décisionnelle unique
    h, m = load["estimated_h"], load["estimated_m"]
    _dur_txt = f"{h}h{m:02d}" if h > 0 else f"{load['total_min']} min"
    if n_u == 0 and n_t == 0:
        _smart_msg = "Rien à faire aujourd'hui — profites-en pour avancer en avance ✓"
    elif n_u == 0:
        _smart_msg = f"Pas de retard ! {n_t} révision{'s' if n_t > 1 else ''} prévue{'s' if n_t > 1 else ''} aujourd'hui · {_dur_txt} estimé"
    elif n_u >= 5:
        _smart_msg = f"Charge critique : {n_u} retards — commence par les urgents, les autres peuvent attendre"
    elif load.get("is_heavy"):
        _smart_msg = f"{n_u} retard{'s' if n_u > 1 else ''} · {_dur_txt} estimé — journée chargée, reporter 1-2 cours si besoin"
    elif done_today > 0 and n_u > 0:
        _smart_msg = f"Bien ! {done_today} faite{'s' if done_today > 1 else ''} · encore {n_u} en retard à traiter"
    else:
        _smart_msg = f"{n_u} en retard · {n_t} prévue{'s' if n_t > 1 else ''} · {_dur_txt} estimé"
    state.smart_lbl.set_text(_smart_msg)
    state.banner_refs["today"].set_text(
        f"{n_t} prévue{'s' if n_t != 1 else ''} aujourd'hui"
    )
    if h > 0:
        state.banner_refs["time"].set_text(f"~{h}h{m:02d} estimé")
    else:
        state.banner_refs["time"].set_text(f"~{load['total_min']} min estimé")

    # UX-06 — Révisions faites aujourd'hui
    state.banner_refs["done_el"].set_visibility(done_today > 0)
    if done_today > 0:
        state.banner_refs["done"].set_text(
            f"{done_today} faite{'s' if done_today > 1 else ''} ✓"
        )

    # IP-06 — Objectif quotidien + barre de progression
    _daily_goal = data_store.preferences.get("daily_goal", 0)
    if _daily_goal and _daily_goal > 0:
        state.banner_refs["goal_el"].set_visibility(True)
        _goal_done = done_today >= _daily_goal
        state.banner_refs["goal"].set_text(
            f"{'✓ ' if _goal_done else ''}{done_today}/{_daily_goal} objectif"
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
        # Barre de progression
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

    # UX-10 — Révisions cette semaine
    state.banner_refs["week_el"].set_visibility(week_count > 0)
    if week_count > 0:
        state.banner_refs["week"].set_text(f"🔥 {week_count} cette semaine")

    # Lacunes critiques
    n_lacunes = local_store.get_critical_weak_points_count()
    state.banner_refs["lacunes_el"].set_visibility(n_lacunes > 0)
    if n_lacunes > 0:
        state.banner_refs["lacunes"].set_text(
            f"{n_lacunes} lacune{'s' if n_lacunes != 1 else ''} critique{'s' if n_lacunes != 1 else ''}"
        )

    # Lacunes à revoir
    try:
        n_revoir = len(local_store.get_lacunes_a_revoir(limit=50))
    except Exception:
        n_revoir = 0
    state.banner_refs["revoir_el"].set_visibility(n_revoir > 0)
    if n_revoir > 0:
        state.banner_refs["revoir"].set_text(f"{n_revoir} à revoir")

    state.banner_refs["heavy"].set_visibility(load["is_heavy"])

    # Montrer/cacher la section badges en fonction de l'activité
    _any_badge = (
        done_today > 0
        or (_daily_goal and _daily_goal > 0)
        or week_count > 0
        or n_lacunes > 0
        or n_revoir > 0
        or load["is_heavy"]
    )
    state.banner_refs["badges_row"].set_visibility(_any_badge)
