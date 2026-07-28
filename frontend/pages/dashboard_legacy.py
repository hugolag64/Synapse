"""
Dashboard Synapse — Vue décisionnelle (Phase E)
------------------------------------------------
Layout :
  • Bannière résumé  : N urgentes · M aujourd'hui · Xh estimé [⚠ Charge lourde]
  • Col gauche (1/4) : Pomodoro + Agenda
  • Col droite (3/4) : Tabs — Aujourd'hui (Urgent | Prévu) | Semaine

Moteur de révision entièrement virtualisé (zéro nouvelle DB Notion).
"""

from nicegui import ui
import asyncio
import datetime
import traceback
from loguru import logger

from frontend.theme import frame
from frontend.components.pomodoro import PomodoroController
from backend.core.notion.service import notion_service
from backend.core.google.calendar_service import calendar_service
from backend.core.reviews.service import review_service
from backend.core.reviews.models import ReviewTask
from backend.core.reviews import local_store
from backend.core.evaluation.models import EvaluationInput
from backend.core.evaluation.service import record_evaluation
from backend.core.reviews.mastery import PROGRESSION_COLORS
from backend.core.reviews.recommendation_service import get_next_action, compute_daily_load
from frontend.components.course_quick_actions import CourseQuickActions
from backend.state.store import data_store
from backend.core.externat.service import externat_service

logger.info("LOADING DASHBOARD MODULE")


# ── Dashboard Page ────────────────────────────────────────────────────────────

async def dashboard_page():
    logger.info("ENTERING DASHBOARD PAGE")
    try:
        _review_context = "college"
        _done_today_ref = {"count": 0}   # UX-06 : révisions validées depuis l'ouverture
        _college_filter = {"value": None}  # PP-05 : filtre par collège actif
        _focus_tasks    = {"list": []}     # IU-01 : tâches pour le mode focus
        _focus_cache    = {"qcm": {}, "lac": {}}  # IU-01 : cache QCM/lacunes pour focus

        pomo = PomodoroController()

        days_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
        months_fr = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
                     "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
        now = datetime.datetime.now()
        date_str = f"{days_fr[now.weekday()]} {now.day} {months_fr[now.month - 1]}"

        # ── Couleurs next_action ──────────────────────────────────────────────
        _NA_COLORS = {
            "red":    "bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-300",
            "orange": "bg-orange-50 text-orange-700 dark:bg-orange-900/20 dark:text-orange-300",
            "blue":   "bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-300",
            "indigo": "bg-violet-50 text-violet-700 dark:bg-violet-900/20 dark:text-violet-300",
            "slate":  "bg-slate-50 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
        }

        with ui.column().classes("w-full gap-6 max-w-7xl mx-auto"):

            # ── Context strip — date + stats primaires ─────────────────────────
            _banner_refs: dict = {}
            with ui.element("div").classes("synapse-context-strip"):
                # Gauche : date + phrase décisionnelle
                with ui.column().classes("gap-0.5"):
                    ui.label(date_str).classes(
                        "synapse-display text-[28px] font-extrabold "
                        "text-slate-900 dark:text-slate-50 tracking-tight capitalize leading-none"
                    )
                    _smart_lbl = ui.label("").classes(
                        "text-[13px] text-slate-500 dark:text-slate-400 font-medium mt-1"
                    )

                # Droite : 3 stats pills
                with ui.row().classes("items-center gap-2 flex-wrap shrink-0"):
                    # Urgentes
                    with ui.element("div").classes(
                        "flex items-center gap-1.5 px-3 py-2 rounded-xl "
                        "bg-red-50 dark:bg-red-900/20 border border-red-100 dark:border-red-800/50"
                    ):
                        ui.icon("priority_high", size="xs").classes("text-red-500")
                        _banner_refs["urgent_n"] = ui.label("…").classes(
                            "text-[15px] font-extrabold tabular-nums leading-none "
                            "text-red-600 dark:text-red-400"
                        )
                        _banner_refs["urgent_lbl"] = ui.label("urgente(s)").classes(
                            "text-[13px] font-semibold text-red-500"
                        )
                    _banner_refs["urgent"] = _banner_refs["urgent_n"]

                    # Aujourd'hui
                    with ui.element("div").classes(
                        "flex items-center gap-1.5 px-3 py-2 rounded-xl "
                        "bg-blue-50 dark:bg-blue-900/20"
                    ):
                        ui.icon("today", size="xs").classes("text-blue-500")
                        _banner_refs["today"] = ui.label("…").classes(
                            "text-[13px] font-semibold text-blue-700 dark:text-blue-400"
                        )

                    # Temps estimé
                    with ui.element("div").classes(
                        "flex items-center gap-1.5 px-3 py-2 rounded-xl "
                        "bg-slate-100 dark:bg-slate-800"
                    ):
                        ui.icon("schedule", size="xs").classes("text-slate-400")
                        _banner_refs["time"] = ui.label("…").classes(
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

            # ── Badges secondaires — inline, masqués si vides ─────────────────
            with ui.row().classes("items-center gap-2 flex-wrap -mt-2"):
                # UX-06 — Faites aujourd'hui
                _banner_refs["done_el"] = ui.element("div").classes(
                    "flex items-center gap-1.5 px-2.5 py-1 rounded-full "
                    "bg-emerald-50 dark:bg-emerald-900/20"
                )
                with _banner_refs["done_el"]:
                    ui.icon("check_circle", size="xs").classes("text-emerald-500")
                    _banner_refs["done"] = ui.label("").classes(
                        "text-[12px] font-semibold text-emerald-700 dark:text-emerald-400"
                    )
                _banner_refs["done_el"].set_visibility(False)

                # IP-06 — Objectif quotidien
                _banner_refs["goal_el"] = ui.element("div").classes(
                    "flex items-center gap-1.5 px-2.5 py-1 rounded-full "
                    "bg-violet-50 dark:bg-violet-900/20 cursor-pointer"
                ).on("click", lambda: ui.navigate.to("/settings"))
                with _banner_refs["goal_el"]:
                    ui.icon("flag", size="xs").classes("text-violet-500")
                    _banner_refs["goal"] = ui.label("").classes(
                        "text-[12px] font-semibold text-violet-700 dark:text-violet-400"
                    )
                _banner_refs["goal_el"].set_visibility(False)

                # UX-10 — Cette semaine
                _banner_refs["week_el"] = ui.element("div").classes(
                    "flex items-center gap-1.5 px-2.5 py-1 rounded-full "
                    "bg-slate-100 dark:bg-slate-800"
                )
                with _banner_refs["week_el"]:
                    _banner_refs["week"] = ui.label("").classes(
                        "text-[12px] font-semibold text-slate-500 dark:text-slate-400"
                    )
                _banner_refs["week_el"].set_visibility(False)

                # Lacunes critiques
                _banner_refs["lacunes_el"] = ui.element("div").classes(
                    "flex items-center gap-1.5 px-2.5 py-1 rounded-full "
                    "bg-red-50 dark:bg-red-900/20 cursor-pointer"
                ).on("click", lambda: ui.navigate.to("/lacunes"))
                with _banner_refs["lacunes_el"]:
                    ui.icon("report_problem", size="xs").classes("text-red-500")
                    _banner_refs["lacunes"] = ui.label("").classes(
                        "text-[12px] font-semibold text-red-700 dark:text-red-400"
                    )
                _banner_refs["lacunes_el"].set_visibility(False)

                # Lacunes à revoir
                _banner_refs["revoir_el"] = ui.element("div").classes(
                    "flex items-center gap-1.5 px-2.5 py-1 rounded-full "
                    "bg-amber-50 dark:bg-amber-900/20 cursor-pointer"
                ).on("click", lambda: ui.navigate.to("/lacunes"))
                with _banner_refs["revoir_el"]:
                    ui.icon("bookmark", size="xs").classes("text-amber-500")
                    _banner_refs["revoir"] = ui.label("").classes(
                        "text-[12px] font-semibold text-amber-700 dark:text-amber-400"
                    )
                _banner_refs["revoir_el"].set_visibility(False)

                # Charge lourde
                _banner_refs["heavy"] = ui.element("div").classes(
                    "flex items-center gap-1.5 px-2.5 py-1 rounded-full "
                    "bg-amber-50 dark:bg-amber-900/20"
                )
                with _banner_refs["heavy"]:
                    ui.icon("warning", size="xs").classes("text-amber-500")
                    ui.label("Charge lourde").classes(
                        "text-[12px] font-semibold text-amber-700 dark:text-amber-400"
                    )
                _banner_refs["heavy"].set_visibility(False)

            # IP-01 — Diagnostic hebdomadaire lundi
            _monday_container = ui.element("div").classes("w-full")
            _is_monday = (datetime.date.today().weekday() == 0)
            _monday_dism_key = f"monday_diag_{datetime.date.today().isoformat()}"

            def _render_monday_diagnostic():
                _monday_container.clear()
                if not _is_monday:
                    return
                if data_store.preferences.get(_monday_dism_key, False):
                    return
                try:
                    _history = local_store.get_all_history()
                    _all = review_service.generate_reviews(context=_review_context, history=_history)
                    _urgent = review_service.get_urgent_tasks(_all)
                    _today  = review_service.get_today_tasks(_all)
                    _n_lac  = local_store.get_open_lacunes_count()

                    # Collège le plus critique (plus d'urgences)
                    from collections import Counter as _Ctr
                    _col_ctr = _Ctr(
                        cg for t in _urgent for cg in (t.college or [])
                    )
                    _weakest_col = _col_ctr.most_common(1)[0][0] if _col_ctr else None

                    # Top 5 cours à prioriser (urgents J30 d'abord)
                    _top5 = sorted(
                        _urgent,
                        key=lambda t: (t.review_type != "J30", t.due_date),
                    )[:5]

                    with _monday_container:
                        with ui.card().classes(
                            "w-full mb-4 rounded-2xl border-2 border-violet-300 dark:border-violet-700 "
                            "bg-violet-50 dark:bg-violet-950/30 p-4 relative overflow-hidden"
                        ):
                            with ui.row().classes("items-start justify-between w-full gap-2"):
                                with ui.row().classes("items-center gap-2"):
                                    ui.icon("auto_awesome", size="sm").classes("text-violet-500 shrink-0")
                                    ui.label("Diagnostic du lundi").classes(
                                        "text-sm font-extrabold text-violet-700 dark:text-violet-300 uppercase tracking-wide"
                                    )
                                def _dismiss():
                                    data_store.set_preference(_monday_dism_key, True)
                                    _monday_container.clear()
                                ui.button(icon="close", on_click=_dismiss).props(
                                    "flat round dense size=xs color=grey-6"
                                ).tooltip("Fermer jusqu'à lundi prochain")

                            with ui.column().classes("w-full gap-2 mt-2"):
                                _lines = [
                                    (f"🔴 {len(_urgent)} révision{'s' if len(_urgent) != 1 else ''} en retard à rattraper cette semaine",
                                     "text-red-700 dark:text-red-300" if _urgent else "text-slate-500"),
                                    (f"📅 {len(_today)} révision{'s' if len(_today) != 1 else ''} prévue{'s' if len(_today) != 1 else ''} aujourd'hui",
                                     "text-blue-700 dark:text-blue-300"),
                                    (f"⚠ {_n_lac} lacune{'s' if _n_lac != 1 else ''} active{'s' if _n_lac != 1 else ''} à retravailler",
                                     "text-amber-700 dark:text-amber-300" if _n_lac > 0 else "text-slate-400"),
                                ]
                                if _weakest_col:
                                    _lines.append((
                                        f"📍 Point faible n°1 : {_weakest_col} ({_col_ctr[_weakest_col]} retard{'s' if _col_ctr[_weakest_col] > 1 else ''})",
                                        "text-orange-700 dark:text-orange-300"
                                    ))
                                for _txt, _cls in _lines:
                                    ui.label(_txt).classes(f"text-[11px] font-semibold {_cls}")

                                if _top5:
                                    ui.separator().classes("my-1 opacity-30")
                                    ui.label("5 cours à prioriser cette semaine :").classes(
                                        "text-[11px] font-bold text-violet-600 dark:text-violet-400 uppercase tracking-wide"
                                    )
                                    for _t in _top5:
                                        with ui.row().classes("items-center gap-1.5"):
                                            ui.badge(_t.type_badge, color="violet").classes("text-[10px] px-1 py-0.5 shrink-0")
                                            ui.label(_t.label).classes(
                                                "text-[11px] text-slate-700 dark:text-slate-300 truncate"
                                            )
                except Exception:
                    pass

            ui.timer(0.1, _render_monday_diagnostic, once=True)

            # ── Zone Hero + Pomodoro côte à côte ──────────────────────────────
            with ui.element("div").classes("grid grid-cols-1 lg:grid-cols-3 gap-5 w-full"):

                # Hero card (2/3) — peuplée par _rebuild_all
                hero_container = ui.element("div").classes("lg:col-span-2 w-full")

                # Pomodoro compact (1/3)
                with ui.element("div").classes("lg:col-span-1"):
                    with ui.card().classes(
                        "w-full rounded-2xl p-5 shadow-sm border border-slate-200 "
                        "dark:border-slate-800 flex flex-col items-center gap-4 relative overflow-hidden"
                    ):
                        ui.element("div").classes(
                            "absolute top-0 right-0 w-28 h-28 bg-violet-50 dark:bg-violet-900/10 "
                            "rounded-full -mr-14 -mt-14 opacity-60"
                        )
                        ui.label("Focus Timer").classes(
                            "text-[11px] font-bold text-violet-400 tracking-widest uppercase z-10"
                        )
                        pomo.lbl_time = ui.label("50:00").classes(
                            "text-6xl font-extrabold text-slate-900 dark:text-slate-100 "
                            "tracking-tighter tabular-nums z-10 pomo-time"
                        )
                        pomo.bar = ui.linear_progress(value=1.0, show_value=False).classes(
                            "w-full rounded-full"
                        ).props("color=deep-purple-4 track-color=deep-purple-1 size=6px")
                        pomo.lbl_status = ui.label("Prêt à démarrer ?").classes(
                            "text-[13px] text-slate-400 dark:text-slate-500 font-medium"
                        )
                        with ui.row().classes("gap-3 z-10"):
                            btn_main = ui.button(on_click=pomo.toggle).props(
                                "round color=deep-purple size=lg unelevated"
                            ).classes("shadow-md shadow-violet-200 dark:shadow-none")
                            with btn_main:
                                pomo.btn_icon = ui.icon("play_arrow")
                            ui.button(icon="restart_alt", on_click=pomo.reset).props(
                                "flat round color=grey-5 size=md"
                            )
                        with ui.row().classes("gap-2 z-10"):
                            prefs = data_store.preferences
                            p1w = prefs.get("pomo_1_work", 25)
                            p2w = prefs.get("pomo_2_work", 50)
                            ui.button(
                                f"{p1w} min", on_click=lambda w=p1w: pomo.set_mode(w)
                            ).props("outline rounded color=deep-purple").classes(
                                "text-[12px] font-semibold px-3"
                            )
                            ui.button(
                                f"{p2w} min", on_click=lambda w=p2w: pomo.set_mode(w)
                            ).props("outline rounded color=deep-purple").classes(
                                "text-[12px] font-semibold px-3"
                            )

                        pomo.timer = ui.timer(1.0, pomo.tick)
                        pomo.timer.deactivate()

                        ui.keyboard(
                            on_key=lambda e: pomo.toggle() if e.action.keydown and e.key.name == 'Space' else None,
                            ignore=['input', 'select', 'textarea'],
                        )

            # ── Grille principale : Révisions | Agenda ─────────────────────────
            with ui.element("div").classes("grid grid-cols-1 lg:grid-cols-4 gap-5 w-full"):

                # ── COL GAUCHE : Agenda + Lacune ───────────────────────────────
                with ui.column().classes("col-span-1 gap-5"):

                    # AGENDA
                    agenda_open_pref = data_store.preferences.get('agenda_open', True)

                    def _on_agenda_toggle(e):
                        data_store.set_preference('agenda_open', e.value)

                    with ui.expansion(
                        value=agenda_open_pref,
                        on_value_change=_on_agenda_toggle,
                    ).classes(
                        "w-full rounded-2xl shadow-sm border border-slate-200 dark:border-slate-800 "
                        "bg-white dark:bg-slate-900"
                    ) as _agenda_exp:
                        with _agenda_exp.add_slot('header'):
                            with ui.row().classes("items-center gap-2 px-5 py-3 w-full"):
                                ui.icon("calendar_today", color="violet").classes(
                                    "bg-violet-50 dark:bg-violet-900/20 p-1.5 rounded-md"
                                )
                                ui.label("Agenda du Jour").classes(
                                    "font-semibold text-slate-800 dark:text-slate-100 text-[15px]"
                                )
                        with ui.column().classes("w-full gap-2 px-5 pb-4"):
                            agenda_col = ui.column().classes("w-full gap-2")

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
                                ).props("flat dense size=xs color=amber-7").classes(
                                    "text-[11px] font-semibold"
                                )
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
                                                ui.label(_ctitle).classes(
                                                    "text-[11px] text-slate-400 truncate"
                                                )

                # ── COL DROITE : Tabs Aujourd'hui | Semaine ────────────────────
                with ui.element("div").classes("col-span-1 lg:col-span-3"):

                    with ui.card().classes(
                        "w-full rounded-2xl shadow-sm border border-slate-100 "
                        "dark:border-slate-800 bg-white dark:bg-slate-900 p-0"
                    ):
                        # Tabs navigation
                        with ui.row().classes(
                            "w-full items-center border-b border-slate-100 dark:border-slate-800 pr-2"
                        ):
                            with ui.tabs().props("dense align=left").classes("flex-1 px-2") as main_tabs:
                                tab_today = ui.tab("Aujourd'hui", icon="today")
                                tab_week  = ui.tab("Semaine",     icon="date_range")

                            # PP-03 — Explication spaced repetition
                            def _open_sr_help():
                                with ui.dialog() as sr_dlg, ui.card().classes(
                                    "w-[440px] max-w-[94vw] rounded-2xl p-0 overflow-hidden "
                                    "bg-white dark:bg-slate-900"
                                ):
                                    with ui.element("div").classes("px-5 pt-4 pb-3 border-b border-slate-100 dark:border-slate-800"):
                                        with ui.row().classes("items-center justify-between"):
                                            ui.label("Pourquoi ces révisions ?").classes(
                                                "text-base font-bold text-slate-900 dark:text-slate-50"
                                            )
                                            ui.button(icon="close", on_click=sr_dlg.close).props("flat round dense size=sm color=grey-7")
                                    with ui.element("div").classes("px-5 py-4 flex flex-col gap-4"):
                                        ui.label(
                                            "Synapse utilise la répétition espacée (spaced repetition), "
                                            "une méthode scientifiquement prouvée pour ancrer les connaissances "
                                            "en mémoire à long terme avec un minimum de temps."
                                        ).classes("text-sm text-slate-600 dark:text-slate-300")
                                        _SR_STEPS = [
                                            ("J3",  "blue",   "3 jours après la 1ʳᵉ lecture", "Ancrage initial — le cours est encore frais mais doit être consolidé."),
                                            ("J7",  "indigo", "7 jours après la 1ʳᵉ lecture", "Consolidation — tes neurones renforcent les connexions récentes."),
                                            ("J14", "violet", "14 jours après la 1ʳᵉ lecture","Renforcement — résiste à la courbe de l'oubli de Ebbinghaus."),
                                            ("J30", "purple", "30 jours après la 1ʳᵉ lecture","Ancrage à long terme — objectif mémorisation EDN durable."),
                                        ]
                                        for badge, col, when, why in _SR_STEPS:
                                            with ui.row().classes("items-start gap-3"):
                                                ui.badge(badge, color=col).classes("text-[11px] font-bold px-2 py-1 shrink-0 mt-0.5")
                                                with ui.column().classes("gap-0.5"):
                                                    ui.label(when).classes("text-sm font-semibold text-slate-800 dark:text-slate-100")
                                                    ui.label(why).classes("text-xs text-slate-400")
                                        ui.element("div").classes("border-t border-slate-100 dark:border-slate-800 pt-3 mt-1")
                                        ui.label("🔁 bonus — cours fragile détecté (QCM raté, lacune critique ou maîtrise < 40%)").classes("text-xs text-slate-500 italic")
                                    with ui.element("div").classes("px-5 pb-4 flex justify-end"):
                                        ui.button("Compris ✓", on_click=sr_dlg.close).props("unelevated rounded color=violet")
                                sr_dlg.open()

                            # IU-01 — Bouton Mode Focus
                            def _open_focus_mode(
                                _ft=_focus_tasks, _fc=_focus_cache
                            ):
                                tasks = list(_ft["list"])
                                if not tasks:
                                    ui.notify("Aucune révision à faire !", type="info")
                                    return
                                _idx = {"i": 0}
                                with ui.dialog(value=True).props("maximized persistent") as _fdlg, \
                                     ui.card().classes(
                                         "w-full h-full max-w-none rounded-none p-0 "
                                         "bg-slate-50 dark:bg-slate-950 flex flex-col overflow-hidden"
                                     ):
                                    with ui.row().classes(
                                        "w-full items-center gap-3 px-6 py-3 shrink-0 "
                                        "border-b border-slate-200 dark:border-slate-800 "
                                        "bg-white dark:bg-slate-900"
                                    ):
                                        ui.icon("center_focus_strong").classes("text-violet-500")
                                        ui.label("Mode Focus").classes(
                                            "text-base font-bold text-slate-900 dark:text-slate-100 flex-1"
                                        )
                                        _ctr = ui.label("").classes(
                                            "text-sm font-mono text-slate-500 "
                                            "px-2 py-0.5 bg-slate-100 dark:bg-slate-800 rounded-full"
                                        )
                                        ui.button(icon="close", on_click=_fdlg.close).props(
                                            "flat round dense size=sm color=grey-7"
                                        ).tooltip("Quitter le mode focus")
                                    with ui.scroll_area().classes("flex-1"):
                                        with ui.element("div").classes("w-full max-w-lg mx-auto p-6"):
                                            _focus_col = ui.column().classes("w-full gap-3")
                                    with ui.row().classes(
                                        "w-full items-center justify-between px-6 py-3 shrink-0 "
                                        "border-t border-slate-200 dark:border-slate-800 "
                                        "bg-white dark:bg-slate-900"
                                    ):
                                        _prev_btn = ui.button("← Précédent").props(
                                            "outline rounded size=sm color=slate"
                                        ).on_click(lambda: _nav(-1))
                                        ui.button("Fermer", on_click=_fdlg.close).props(
                                            "flat rounded size=sm color=grey"
                                        )
                                        _next_btn = ui.button("Suivant →").props(
                                            "unelevated rounded size=sm color=violet"
                                        ).on_click(lambda: _nav(1))

                                def _render_focus():
                                    _focus_col.clear()
                                    t = tasks[_idx["i"]]
                                    _ctr.set_text(f"{_idx['i'] + 1} / {len(tasks)}")
                                    _prev_btn.set_enabled(_idx["i"] > 0)
                                    _next_btn.set_enabled(_idx["i"] < len(tasks) - 1)
                                    _render_review_card(
                                        _focus_col, t,
                                        _on_validate_review, _on_postpone, _on_ignore,
                                        qcm_info=_fc["qcm"].get(t.course_id),
                                        lacune_count=_fc["lac"].get(t.course_id, 0),
                                    )

                                def _nav(delta: int):
                                    ni = _idx["i"] + delta
                                    if 0 <= ni < len(tasks):
                                        _idx["i"] = ni
                                        _render_focus()
                                    elif ni >= len(tasks):
                                        _fdlg.close()
                                        ui.notify("✓ Focus terminé — toutes les révisions traitées !", type="positive")

                                _render_focus()

                            ui.button(
                                icon="center_focus_strong", on_click=_open_focus_mode
                            ).props(
                                "flat round dense size=sm"
                            ).classes("text-slate-300 dark:text-slate-600").tooltip("Mode Focus — une révision à la fois")

                            ui.button(icon="help_outline", on_click=_open_sr_help).props(
                                "flat round dense size=sm"
                            ).classes("text-slate-300 dark:text-slate-600").tooltip("Pourquoi ces révisions ?")

                        # PP-05 — Filtre par collège
                        college_filter_row = ui.row().classes(
                            "w-full px-4 py-2 gap-1.5 flex-wrap items-center "
                            "border-b border-slate-50 dark:border-slate-800/60"
                        )
                        _college_chip_refs: dict = {}

                        def _render_college_chips(all_tasks):
                            college_filter_row.clear()
                            _college_chip_refs.clear()
                            colleges_in_tasks = sorted({
                                cg for t in all_tasks for cg in (t.college or [])
                            })
                            if len(colleges_in_tasks) <= 1:
                                college_filter_row.set_visibility(False)
                                return
                            college_filter_row.set_visibility(True)
                            with college_filter_row:
                                ui.label("Filtre :").classes(
                                    "text-[11px] font-bold text-slate-400 uppercase tracking-wide shrink-0"
                                )
                                active_col = _college_filter["value"]

                                def _make_chip(label, college_val):
                                    is_active = (college_val == active_col)
                                    btn = ui.button(label).props(
                                        f"{'unelevated' if is_active else 'outline'} rounded dense size=xs "
                                        f"color={'violet' if is_active else 'grey'}"
                                    ).classes("text-[11px] font-semibold")
                                    def _on_click(v=college_val):
                                        _college_filter["value"] = None if _college_filter["value"] == v else v
                                        _rebuild_all()
                                    btn.on_click(_on_click)
                                    return btn

                                _make_chip("Tout", None)
                                for cg in colleges_in_tasks:
                                    _make_chip(cg, cg)

                        with ui.tab_panels(main_tabs, value=tab_today).classes("w-full p-0"):

                            # ── TAB AUJOURD'HUI ────────────────────────────────
                            with ui.tab_panel(tab_today).classes("p-4 w-full"):
                                with ui.element("div").classes(
                                    "grid grid-cols-1 md:grid-cols-2 gap-4 w-full items-stretch"
                                ):
                                    # Colonne Urgent
                                    with _review_column("🔴 Urgent", "red", "alarm"):
                                        urgent_col = ui.column().classes("w-full gap-2")

                                    # Colonne Aujourd'hui
                                    with _review_column("📅 Aujourd'hui", "blue", "today"):
                                        today_col = ui.column().classes("w-full gap-2")

                            # ── TAB SEMAINE ────────────────────────────────────
                            with ui.tab_panel(tab_week).classes("p-4 w-full"):
                                with ui.scroll_area().classes("w-full").style("max-height:640px"):
                                    week_col = ui.column().classes("w-full gap-1")

        # ── Helpers ───────────────────────────────────────────────────────────

        _DAYS_FR   = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
        _MONTHS_FR = ["jan", "fév", "mar", "avr", "mai", "juin",
                      "juil", "août", "sep", "oct", "nov", "déc"]

        def _day_label(d: datetime.date) -> str:
            today = datetime.date.today()
            if d == today:
                return "Aujourd'hui"
            if d == today + datetime.timedelta(1):
                return "Demain"
            return f"{_DAYS_FR[d.weekday()]} {d.day} {_MONTHS_FR[d.month - 1]}"

        # PP-07 — Bilan de fin de session
        _bilan_shown = {"shown": False}

        def _show_bilan_session(done_today: int):
            if _bilan_shown["shown"]:
                return
            _bilan_shown["shown"] = True
            # §8 — Célébration légère quand 0 urgences atteint
            try:
                ui.run_javascript("synapseConfetti()")
            except Exception:
                pass

            try:
                history = local_store.get_all_history()
                today_str = datetime.date.today().strftime("%Y-%m-%d")
                today_sessions = [
                    h for h in history
                    if getattr(h, "done_date", None) and str(getattr(h, "done_date", "")).startswith(today_str)
                ]
                n_done = len(today_sessions)
                try:
                    n_lacunes = local_store.get_open_lacunes_count()
                except Exception:
                    n_lacunes = 0
                try:
                    _wk_ago = (datetime.date.today() - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
                    week_sessions = [
                        h for h in history
                        if getattr(h, "done_date", None) and str(getattr(h, "done_date", "")) >= _wk_ago
                    ]
                    n_week = len(week_sessions)
                except Exception:
                    n_week = done_today
            except Exception:
                n_done = done_today
                n_lacunes = 0
                n_week = done_today

            with ui.dialog() as bilan_dlg, ui.card().classes(
                "w-[420px] max-w-[94vw] rounded-2xl p-0 overflow-hidden "
                "bg-white dark:bg-slate-900"
            ):
                with ui.element("div").classes(
                    "px-6 pt-6 pb-4 text-center flex flex-col items-center gap-3"
                ):
                    ui.label("🎉").classes("text-5xl")
                    ui.label("Révisions du jour terminées !").classes(
                        "text-xl font-extrabold text-slate-900 dark:text-slate-50"
                    )
                    ui.label("Plus aucun retard. Excellent travail.").classes(
                        "text-sm text-slate-400"
                    )

                with ui.element("div").classes(
                    "mx-6 mb-4 rounded-xl bg-slate-50 dark:bg-slate-800 p-4 "
                    "grid grid-cols-3 gap-4"
                ):
                    for icon_n, val, lbl in [
                        ("check_circle", str(n_done), "Aujourd'hui"),
                        ("date_range",   str(n_week), "Cette semaine"),
                        ("report_problem", str(n_lacunes), "Lacunes ouvertes"),
                    ]:
                        with ui.column().classes("items-center gap-1"):
                            ui.icon(icon_n, size="sm").classes("text-violet-400")
                            ui.label(val).classes(
                                "text-2xl font-extrabold tabular-nums text-slate-800 dark:text-slate-100"
                            )
                            ui.label(lbl).classes("text-[11px] text-slate-400 text-center")

                with ui.element("div").classes(
                    "px-6 pb-6 flex flex-col gap-2"
                ):
                    ui.button(
                        "Voir ma progression",
                        on_click=lambda: (bilan_dlg.close(), ui.navigate.to("/stats")),
                    ).props("unelevated rounded color=violet").classes("w-full font-semibold")
                    ui.button(
                        "Fermer",
                        on_click=bilan_dlg.close,
                    ).props("flat rounded color=grey-7").classes("w-full")

            bilan_dlg.open()

        # UX-07 — État vide standardisé avec CTA optionnel
        def _empty_state(
            container,
            message: str,
            icon_name: str = "check_circle",
            action_label: str | None = None,
            action_fn=None,
        ):
            with container:
                with ui.column().classes("w-full items-center py-6 gap-2 text-slate-400"):
                    ui.icon(icon_name, size="lg").classes("opacity-40")
                    ui.label(message).classes("text-xs text-center font-medium")
                    if action_label and action_fn:
                        ui.button(action_label, on_click=action_fn).props(
                            "flat dense size=sm color=violet"
                        ).classes("text-[11px] font-semibold mt-1")

        def _update_banner(load: dict, done_today: int = 0, week_count: int = 0):
            n_u = load["urgent_count"]
            n_t = load["today_count"]
            _banner_refs["urgent_n"].set_text(str(n_u))
            _banner_refs["urgent_lbl"].set_text(
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
            _smart_lbl.set_text(_smart_msg)
            _banner_refs["today"].set_text(
                f"{n_t} prévue{'s' if n_t != 1 else ''} aujourd'hui"
            )
            h, m = load["estimated_h"], load["estimated_m"]
            if h > 0:
                _banner_refs["time"].set_text(f"~{h}h{m:02d} estimé")
            else:
                _banner_refs["time"].set_text(f"~{load['total_min']} min estimé")
            # UX-06 — Révisions faites aujourd'hui
            _banner_refs["done_el"].set_visibility(done_today > 0)
            if done_today > 0:
                _banner_refs["done"].set_text(
                    f"{done_today} faite{'s' if done_today > 1 else ''} ✓"
                )
            # IP-06 — Objectif quotidien
            _daily_goal = data_store.preferences.get("daily_goal", 0)
            if _daily_goal and _daily_goal > 0:
                _banner_refs["goal_el"].set_visibility(True)
                _goal_pct = min(done_today / _daily_goal, 1.0)
                _goal_done = done_today >= _daily_goal
                _banner_refs["goal"].set_text(
                    f"{'✓ ' if _goal_done else ''}{done_today}/{_daily_goal} objectif"
                )
                _banner_refs["goal_el"].classes(
                    remove="bg-violet-50 dark:bg-violet-900/20 bg-green-50 dark:bg-green-900/20"
                )
                _banner_refs["goal_el"].classes(
                    add="bg-green-50 dark:bg-green-900/20" if _goal_done else "bg-violet-50 dark:bg-violet-900/20"
                )
                _banner_refs["goal"].classes(
                    remove="text-violet-700 dark:text-violet-400 text-green-700 dark:text-green-400"
                )
                _banner_refs["goal"].classes(
                    add="text-green-700 dark:text-green-400" if _goal_done else "text-violet-700 dark:text-violet-400"
                )
            else:
                _banner_refs["goal_el"].set_visibility(False)
            # UX-10 — Révisions cette semaine
            _banner_refs["week_el"].set_visibility(week_count > 0)
            if week_count > 0:
                _banner_refs["week"].set_text(f"🔥 {week_count} cette semaine")
            # Lacunes critiques
            n_lacunes = local_store.get_critical_weak_points_count()
            _banner_refs["lacunes_el"].set_visibility(n_lacunes > 0)
            if n_lacunes > 0:
                _banner_refs["lacunes"].set_text(
                    f"{n_lacunes} lacune{'s' if n_lacunes != 1 else ''} critique{'s' if n_lacunes != 1 else ''}"
                )
            # Lacunes à revoir
            try:
                n_revoir = len(local_store.get_lacunes_a_revoir(limit=50))
            except Exception:
                n_revoir = 0
            _banner_refs["revoir_el"].set_visibility(n_revoir > 0)
            if n_revoir > 0:
                _banner_refs["revoir"].set_text(
                    f"{n_revoir} à revoir"
                )
            _banner_refs["heavy"].set_visibility(load["is_heavy"])

        # ── Dialog lacune inline ──────────────────────────────────────────────

        def _open_lacune_inline_dialog(task: ReviewTask) -> None:
            """Mini-modale pour créer une lacune liée au cours sans quitter le Dashboard."""
            with ui.dialog() as dlg:
                with ui.card().classes(
                    "w-[420px] max-w-[95vw] p-0 rounded-2xl overflow-hidden shadow-xl"
                ):
                    with ui.element("div").classes(
                        "px-5 py-4 border-b border-slate-100 dark:border-slate-800"
                    ):
                        with ui.row().classes("items-center justify-between"):
                            ui.label("Ajouter une lacune").classes(
                                "font-bold text-slate-800 dark:text-slate-100"
                            )
                            ui.button(icon="close", on_click=dlg.close).props(
                                "flat round dense size=sm color=grey"
                            )
                    with ui.element("div").classes("px-5 py-4 flex flex-col gap-3"):
                        ui.label(task.label).classes(
                            "text-xs text-slate-400 truncate"
                        ).tooltip(task.label)
                        inp_detail = ui.input(
                            label="Ce qui n'est pas clair",
                            placeholder="Ex: mécanisme de la douleur viscérale...",
                        ).props("outlined dense").classes("w-full")
                        inp_cat = ui.select(
                            label="Catégorie",
                            options=["anatomie", "physiopathologie", "traitement",
                                     "diagnostic", "autre"],
                            value="autre",
                        ).props("outlined dense").classes("w-full")
                    with ui.element("div").classes(
                        "px-5 py-3 bg-slate-50 dark:bg-slate-800/50 "
                        "border-t border-slate-100 dark:border-slate-800 "
                        "flex justify-end gap-2"
                    ):
                        ui.button("Annuler", on_click=dlg.close).props("flat color=grey-8")
                        def _save_lacune(_dlg=dlg, _task=task):
                            detail = inp_detail.value.strip()
                            if not detail:
                                ui.notify("Décris la lacune avant de sauvegarder", type="warning")
                                return
                            local_store.add_weak_point(
                                course_id=_task.course_id,
                                course_title=_task.course_title,
                                item_number=_task.item_number or "",
                                category=inp_cat.value,
                                detail=detail,
                                severity=2,
                                source_session_id=None,
                            )
                            _dlg.close()
                            ui.notify("Lacune notée ✓", type="positive")
                        ui.button("Ajouter", on_click=_save_lacune).props(
                            "unelevated color=amber rounded"
                        ).classes("font-semibold")
            dlg.open()

        # ── Render : carte révision (vue Urgent / Aujourd'hui) ────────────────

        def _render_review_card(
            container,
            task: ReviewTask,
            on_done=None,
            on_postpone=None,
            on_ignore=None,
            qcm_info: dict | None = None,
            lacune_count: int = 0,
        ):
            """Carte de révision avec next_action, badge QCM et badge lacune."""
            col_map = {
                "J3": "blue", "J7": "indigo", "J14": "violet",
                "J30": "purple", "bonus": "orange", "qcm_error": "red", "manuel": "orange",
            }
            badge_color = col_map.get(task.review_type, "slate")
            _REVIEW_TYPE_TIPS = {
                "J3":       "Révision J+3 — 3 jours après la 1ʳᵉ lecture (ancrage initial)",
                "J7":       "Révision J+7 — 7 jours après la 1ʳᵉ lecture (consolidation)",
                "J14":      "Révision J+14 — 2 semaines (renforcement à moyen terme)",
                "J30":      "Révision J+30 — 1 mois (mémorisation à long terme)",
                "bonus":    "Révision bonus — cours fragile ou lacunes détectées",
                "qcm_error":"Révision QCM — cours raté en QCM, à retravailler",
                "manuel":   "Révision manuelle — planifiée manuellement",
            }
            _DATE_SOURCE_LABELS = {
                "notion": "📅 Date Notion (planification manuelle)",
                "sm2":    "🧠 Date SM-2 (intervalle adaptatif)",
                "fixe":   "📐 Date fixe (J+offset théorique)",
            }
            _type_tip = _REVIEW_TYPE_TIPS.get(task.review_type, task.review_type)
            if task.date_source:
                _type_tip += f"\n{_DATE_SOURCE_LABELS.get(task.date_source, task.date_source)}"
            lec = task.nb_lectures

            # Extraire score QCM pour le moteur de recommandation
            last_qcm_score: float | None = None
            if qcm_info:
                last_qcm_score = qcm_info.get("last_score")

            # Stage actif pour le boost contextuel
            try:
                from backend.core.externat.service import externat_service as _ext_svc
                _stage = _ext_svc.get_active_stage()
                _stage_college = _stage.college_notion if _stage else None
            except Exception:
                _stage_college = None

            na = get_next_action(
                task,
                last_qcm_score=last_qcm_score,
                lacune_count=lacune_count,
                stage_college=_stage_college,
            )
            na_cls = _NA_COLORS.get(na.color, _NA_COLORS["slate"])

            # Tooltip maîtrise pour le titre
            mastery_tip = ""
            if task.mastery_level:
                mastery_tip = f"{task.mastery_level.capitalize()} {task.mastery_score}%"
                if task.mastery_reasons:
                    mastery_tip += " · " + " · ".join(task.mastery_reasons[:2])

            with container:
                with ui.card().classes(
                    "w-full p-3 rounded-xl border border-slate-100 dark:border-slate-700 "
                    "shadow-sm hover:shadow-md transition-all"
                ) as card:
                    with ui.column().classes("w-full gap-2 min-w-0"):

                        # ── Badges (simplifiés) ───────────────────────────────
                        with ui.row().classes("items-center gap-1.5 flex-wrap"):
                            ui.badge(task.type_badge, color=badge_color).classes(
                                "text-[11px] font-bold px-1.5 py-0.5 shrink-0"
                            ).tooltip(_type_tip)
                            if task.context == "ue":
                                ui.badge("UE", color="teal").classes(
                                    "text-[11px] px-1.5 py-0.5 shrink-0"
                                )
                            days_future = (task.due_date - datetime.date.today()).days
                            if days_future > 0:
                                ui.badge(f"dans {days_future}j", color="blue").classes(
                                    "text-[11px] px-1.5 py-0.5 shrink-0"
                                )
                            # Lectures : compact, sans rouge si 0
                            if lec > 0:
                                ui.badge(f"{lec}×", color="green").classes(
                                    "text-[11px] px-1.5 py-0.5 shrink-0 opacity-70"
                                ).tooltip(f"Lu {lec} fois")

                            # QCM : seulement si score raté (<70 %)
                            if qcm_info:
                                from backend.core.qcm.service import score_color as _sc, QCM_PASS_THRESHOLD as _thresh
                                sc  = qcm_info["last_score"]
                                if sc is not None and sc < _thresh:
                                    raw = qcm_info.get("last_raw") or f"{int(sc)}%"
                                    ui.badge(
                                        f"QCM {raw}",
                                        color=_sc(sc),
                                    ).classes(
                                        "text-[11px] font-bold px-1.5 py-0.5 shrink-0"
                                    ).tooltip(f"Dernier QCM : {raw} — à retravailler")

                            # Lacunes : seulement si > 0
                            if lacune_count > 0:
                                ui.badge(
                                    f"⚠ {lacune_count}",
                                    color="amber",
                                ).classes(
                                    "text-[11px] font-bold px-1.5 py-0.5 shrink-0"
                                ).tooltip(
                                    f"{lacune_count} lacune{'s' if lacune_count > 1 else ''} active{'s' if lacune_count > 1 else ''}"
                                )

                        # ── Titre (tooltip = maîtrise si disponible) ──────────
                        _title_tip = mastery_tip or task.label
                        ui.label(task.label).classes(
                            "text-sm font-semibold text-slate-900 dark:text-slate-100 "
                            "leading-snug w-full"
                        ).style(
                            "display:-webkit-box;-webkit-line-clamp:2;"
                            "-webkit-box-orient:vertical;overflow:hidden;word-break:break-word"
                        ).tooltip(_title_tip)

                        # ── Next action recommandée ───────────────────────────
                        with ui.row().classes(
                            f"items-center gap-1.5 w-full px-2 py-1 rounded-lg {na_cls}"
                        ):
                            ui.icon(na.icon, size="xs").classes("shrink-0")
                            ui.label(na.label).classes(
                                "text-[11px] font-bold shrink-0"
                            )
                            ui.label(f"· {na.duration_min} min").classes(
                                "text-[11px] shrink-0 opacity-80"
                            )
                            if na.reason:
                                ui.label(f"— {na.reason}").classes(
                                    "text-[11px] opacity-60 truncate min-w-0 flex-1"
                                )

                        # ── Actions ───────────────────────────────────────────
                        # IU-06 — état du chrono par carte
                        _tstate = {"t0": None}

                        with ui.row().classes(
                            "w-full items-center gap-1 pt-1.5 border-t "
                            "border-slate-100 dark:border-slate-700"
                        ):
                            # IU-06 — Timer : label temps + bouton ⏱
                            _tel = ui.label("").classes(
                                "text-[11px] font-mono text-orange-500 "
                                "dark:text-orange-400 shrink-0"
                            ).style("display:none")

                            def _toggle_timer(_ts=_tstate, _lbl=_tel):
                                if _ts["t0"] is None:
                                    _ts["t0"] = datetime.datetime.now()
                                    _lbl.style("display:inline")
                                    _ctmr.activate()
                                else:
                                    _ts["t0"] = None
                                    _lbl.set_text("")
                                    _lbl.style("display:none")
                                    _ctmr.deactivate()

                            ui.button("⏱").props(
                                "flat round dense size=xs"
                            ).classes(
                                "text-slate-300 hover:text-orange-500 shrink-0"
                            ).tooltip("Chronométrer (auto-remplit la durée)").on_click(
                                _toggle_timer
                            )

                            # UX-02 — Bouton 1-clic "✓ Fait" (validation rapide score moyen)
                            def _make_direct_val(t, c, _ts=_tstate):
                                async def _h():
                                    _dur = 20
                                    if _ts["t0"] is not None:
                                        _dur = max(1, int(
                                            (datetime.datetime.now() - _ts["t0"]).total_seconds() / 60
                                        ))
                                    await validate_review_with_feedback(
                                        t, c, ["révision"], _dur, 3, "moyen"
                                    )
                                return _h
                            ui.button("✓ Fait").props(
                                "unelevated rounded dense size=sm color=green"
                                " aria-label='Valider la révision'"
                            ).classes("text-[11px] font-bold px-2").on_click(
                                _make_direct_val(task, card)
                            ).tooltip("Valider rapidement (confiance moyenne)")

                            with ui.button(icon="tune").props(
                                "flat round dense size=sm color=green"
                                " aria-label='Feedback détaillé'"
                            ).tooltip("Valider avec feedback détaillé"):
                                with ui.menu() as _val_menu:
                                    _CONF_EMOJIS = [
                                        (1, "😰", "red",    "Très difficile"),
                                        (2, "😟", "orange", "Difficile"),
                                        (3, "😐", "blue",   "Moyen"),
                                        (4, "😊", "teal",   "Facile"),
                                        (5, "🔥", "green",  "Parfait !"),
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
                                            await validate_review_with_feedback(
                                                t, c, ["révision"], _dur, score, _diff
                                            )
                                        return _h

                                    with ui.element("div").classes("px-3 pt-3 pb-2 flex flex-col gap-2"):
                                        ui.label("Confiance ?").classes(
                                            "text-[11px] font-bold text-slate-400 uppercase tracking-wide"
                                        )
                                        with ui.row().classes("gap-1 justify-center mt-1"):
                                            for _score, _emoji, _col, _tip in _CONF_EMOJIS:
                                                ui.button(_emoji).props(
                                                    "flat round dense"
                                                ).classes(
                                                    f"text-lg text-{_col}-500 "
                                                    f"hover:bg-{_col}-50 dark:hover:bg-slate-700"
                                                ).on_click(
                                                    _make_quick_val(
                                                        _score, task, card, _val_menu, _base_dur
                                                    )
                                                ).tooltip(f"{_tip} ({_score}/5)")

                                    ui.separator().classes("mb-1")
                                    ui.menu_item(
                                        "🔍  Détailler...",
                                        on_click=lambda t=task, c=card: open_session_feedback_dialog(t, c),
                                    ).classes("text-xs text-slate-500 font-medium")
                                    ui.separator()
                                    ui.menu_item(
                                        "⚠  Lacune...",
                                        on_click=lambda t=task: _open_lacune_inline_dialog(t),
                                    ).classes("text-xs text-amber-600 font-medium")

                            if task.has_pdf:
                                ui.button(
                                    icon="picture_as_pdf",
                                    on_click=lambda tid=task.course_id: ui.navigate.to(
                                        f"/pdf/{tid}", new_tab=True
                                    ),
                                ).props("flat round dense size=sm").classes("text-red-400").tooltip("Ouvrir PDF")

                            if task.agregation_fiche_edn:
                                ui.button(
                                    icon="auto_stories",
                                    on_click=lambda url=task.agregation_fiche_edn: ui.navigate.to(
                                        url, new_tab=True
                                    ),
                                ).props("flat round dense size=sm").classes("text-slate-400").tooltip("Fiche EDN")

                            ui.element("div").classes("flex-1")

                            # IU-06 — ui.timer de tick (désactivé au départ)
                            def _tick_fn(_ts=_tstate, _lbl=_tel):
                                if _ts["t0"]:
                                    _e = int((datetime.datetime.now() - _ts["t0"]).total_seconds())
                                    _m, _s = divmod(_e, 60)
                                    _lbl.set_text(f"{_m:02d}:{_s:02d}")
                            _ctmr = ui.timer(1.0, _tick_fn)
                            _ctmr.deactivate()

                            if on_postpone or on_ignore:
                                # UX-03 — Reporter moins visible
                                with ui.button(icon="more_horiz").props(
                                    "flat round dense size=xs"
                                ).classes(
                                    "text-slate-300 dark:text-slate-600 "
                                    "opacity-60 hover:opacity-100 transition-opacity"
                                ).tooltip("Reporter / Ignorer"):
                                    with ui.menu().classes("text-sm"):
                                        def wrap_post_main(t, c, d):
                                            async def _h(): await on_postpone(t, c, d)
                                            return _h
                                        def wrap_ign_main(t, c):
                                            async def _h(): await on_ignore(t, c)
                                            return _h

                                        ui.menu_item(
                                            "↻  Décaler de +1 jour",
                                            on_click=wrap_post_main(task, card, 1),
                                        ).classes("text-xs")
                                        ui.menu_item(
                                            "↻  Décaler de +3 jours",
                                            on_click=wrap_post_main(task, card, 3),
                                        ).classes("text-xs")
                                        ui.menu_item(
                                            "↻  Décaler de +7 jours",
                                            on_click=wrap_post_main(task, card, 7),
                                        ).classes("text-xs text-amber-600").tooltip(
                                            "⚠ Peut créer un retard critique sur ce cours"
                                        )
                                        ui.separator()
                                        ui.menu_item(
                                            "✕  Ignorer cette révision",
                                            on_click=wrap_ign_main(task, card),
                                        ).classes("text-xs text-red-400")

        # ── Render : ligne compacte (vue Semaine) ─────────────────────────────

        def _render_task_row(
            container,
            task: ReviewTask,
            on_done=None,
            on_postpone=None,
            on_ignore=None,
        ):
            """Vue Semaine — ligne compacte 1 niveau."""
            col_map = {
                "J3": "blue", "J7": "indigo", "J14": "violet",
                "J30": "purple", "bonus": "orange", "qcm_error": "red", "manuel": "orange",
            }
            badge_color = col_map.get(task.review_type, "slate")
            _REVIEW_TYPE_TIPS_ROW = {
                "J3":       "Révision J+3 — ancrage initial",
                "J7":       "Révision J+7 — consolidation",
                "J14":      "Révision J+14 — renforcement moyen terme",
                "J30":      "Révision J+30 — mémorisation long terme",
                "bonus":    "Cours fragile ou lacunes détectées",
                "qcm_error":"Raté en QCM — à retravailler",
                "manuel":   "Révision manuelle",
            }
            _type_tip_row = _REVIEW_TYPE_TIPS_ROW.get(task.review_type, task.review_type)
            na = get_next_action(task)

            def _wrap_val(t, el, a, dur, conf, diff):
                async def _h(): await validate_review_with_feedback(t, el, a, dur, conf, diff)
                return _h

            def _wrap_post(t, el, d):
                async def _h(): await on_postpone(t, el, d)
                return _h

            def _wrap_ign(t, el):
                async def _h(): await on_ignore(t, el)
                return _h

            with container:
                with ui.element("div").classes(
                    "w-full px-3 py-2 rounded-lg flex items-center gap-2 "
                    "hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors"
                ) as row_el:
                    # Badge type
                    ui.badge(task.type_badge, color=badge_color).classes(
                        "text-[11px] font-bold px-1.5 py-0.5 shrink-0"
                    ).tooltip(_type_tip_row)

                    # Maîtrise (uniquement si critique/fragile)
                    if task.mastery_level in ("critique", "fragile"):
                        m_color = PROGRESSION_COLORS.get(task.mastery_level, "slate")
                        ui.badge(
                            task.mastery_level.capitalize(), color=m_color
                        ).classes("text-[11px] px-1 py-0.5 shrink-0")

                    # Titre (flex-1 — prend tout l'espace disponible)
                    ui.label(task.label).classes(
                        "text-sm text-slate-700 dark:text-slate-200 flex-1 min-w-0 "
                        "font-medium truncate"
                    ).tooltip(task.course_title)

                    # Durée estimée
                    ui.label(f"{na.duration_min}min").classes(
                        "text-[11px] text-slate-400 shrink-0 tabular-nums"
                    )

                    # ✓ Valider en 1 clic (20min · conf.3 · moyen par défaut)
                    ui.button(
                        icon="check_circle",
                        on_click=_wrap_val(task, row_el, ["révision"], 20, 3, "moyen"),
                    ).props("flat round dense size=md color=green").classes(
                        "shrink-0"
                    ).tooltip("Valider (20min · conf.3)")

                    # ⋯ Menu : variantes de validation + reporter + ignorer
                    with ui.button(icon="more_horiz").props(
                        "flat round dense size=sm"
                    ).classes("text-slate-400 shrink-0"):
                        with ui.menu().classes("text-sm"):
                            ui.menu_item(
                                "⚡  Rapide — 10min",
                                on_click=_wrap_val(task, row_el, ["révision"], 10, 4, "facile"),
                            ).classes("text-xs")
                            ui.menu_item(
                                "💪  Difficile — 30min",
                                on_click=_wrap_val(task, row_el, ["révision"], 30, 2, "difficile"),
                            ).classes("text-xs")
                            ui.menu_item(
                                "🔍  Détailler…",
                                on_click=lambda t=task, el=row_el: open_session_feedback_dialog(t, el),
                            ).classes("text-xs")
                            ui.separator()
                            ui.menu_item(
                                "↻  Décaler +1j",
                                on_click=_wrap_post(task, row_el, 1),
                            ).classes("text-xs")
                            ui.menu_item(
                                "↻  Décaler +3j",
                                on_click=_wrap_post(task, row_el, 3),
                            ).classes("text-xs")
                            ui.menu_item(
                                "↻  Décaler +7j",
                                on_click=_wrap_post(task, row_el, 7),
                            ).classes("text-xs")
                            ui.separator()
                            ui.menu_item(
                                "✕  Ignorer",
                                on_click=_wrap_ign(task, row_el),
                            ).classes("text-xs text-red-400")

        # ── "Voir plus" helper ────────────────────────────────────────────────

        def _add_voir_plus(container, remaining, render_fn, on_validate, on_postpone, on_ignore):
            """Ajoute un bloc masqué + bouton 'Voir X de plus'."""
            with container:
                extra_col = ui.column().classes("w-full gap-2")
            extra_col.set_visibility(False)

            for t in remaining:
                render_fn(extra_col, t, on_validate, on_postpone, on_ignore)

            with container:
                btn = ui.button(
                    f"Voir {len(remaining)} de plus ↓"
                ).props("flat dense size=sm color=blue-grey").classes(
                    "w-full text-xs mt-1"
                )

                def _toggle(b=btn, ec=extra_col, rem=remaining):
                    vis = not ec.visible
                    ec.set_visibility(vis)
                    b.set_text("Masquer ↑" if vis else f"Voir {len(rem)} de plus ↓")

                btn.on_click(_toggle)

        # ── Rebuild semaine ───────────────────────────────────────────────────

        def _rebuild_week(all_tasks):
            from itertools import groupby
            week_col.clear()
            pool = (
                review_service.get_today_tasks(all_tasks) +
                review_service.get_upcoming_tasks(all_tasks, days=7)
            )
            if not pool:
                _empty_state(week_col, "Aucune révision cette semaine", "event_available")
                return
            pool_sorted = sorted(pool, key=lambda t: t.due_date)
            for day_date, group in groupby(pool_sorted, key=lambda t: t.due_date):
                tasks_day = list(group)
                with week_col:
                    with ui.row().classes("items-center gap-2 px-2 pt-3 pb-0.5"):
                        ui.label(_day_label(day_date)).classes(
                            "text-[11px] font-bold uppercase tracking-wide "
                            "text-slate-400 dark:text-slate-500 flex-1"
                        )
                        ui.badge(str(len(tasks_day)), color="slate").classes("text-[11px]")
                    ui.separator().classes("mb-0.5 opacity-50")
                for t in tasks_day:
                    _render_task_row(week_col, t, _on_validate_review, _on_postpone, _on_ignore)

        # ── Rebuild complet ───────────────────────────────────────────────────

        def _rebuild_all():
            history   = local_store.get_all_history()
            all_tasks = review_service.generate_reviews(
                context=_review_context, history=history
            )
            # Stage boost : légère priorité aux cours du stage actif (≤ 3j de retard)
            all_tasks = externat_service.apply_stage_boost(all_tasks)

            # PP-05 — Filtre par collège actif
            _render_college_chips(all_tasks)
            _active_college = _college_filter["value"]
            if _active_college:
                all_tasks = [
                    t for t in all_tasks
                    if _active_college in (t.college or [])
                ]

            urgent      = review_service.get_urgent_tasks(all_tasks)
            today_tasks = review_service.get_today_tasks(all_tasks)

            # IU-01 — Mise à jour du pool Focus Mode
            _focus_tasks["list"] = urgent + today_tasks

            # UX-10 — Comptage révisions cette semaine
            from datetime import datetime, timedelta
            _week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            _week_count = sum(
                1 for h in history
                if getattr(h, "done_date", None) and str(getattr(h, "done_date", "")) >= _week_ago
            )

            # Bannière
            load = compute_daily_load(urgent, today_tasks)
            _update_banner(load, done_today=_done_today_ref["count"], week_count=_week_count)

            # UX-01 — Hero card : tâche la plus urgente
            hero_container.classes(remove="opacity-0")
            hero_container.clear()
            _first_urgent = urgent[0] if urgent else (today_tasks[0] if today_tasks else None)
            if _first_urgent:
                with hero_container:
                    with ui.element("div").classes(
                        "w-full h-full synapse-hero-card flex flex-col gap-4"
                    ):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("bolt", size="sm").classes(
                                "text-violet-500 dark:text-violet-400 shrink-0"
                            )
                            ui.label("Priorité maintenant").classes(
                                "text-[12px] font-bold uppercase tracking-wider "
                                "text-violet-500 dark:text-violet-400"
                            )
                            ui.badge(
                                _first_urgent.type_badge, color="deep-purple"
                            ).classes("text-[12px] font-bold px-2 py-0.5 shrink-0 ml-1")
                        ui.label(_first_urgent.label).classes(
                            "text-[17px] font-bold text-slate-900 dark:text-slate-100 "
                            "leading-snug"
                        ).tooltip(_first_urgent.label)
                        _na_hero = get_next_action(_first_urgent)
                        ui.label(f"{_na_hero.label} · {_na_hero.duration_min} min estimé").classes(
                            "text-[13px] text-slate-500 dark:text-slate-400"
                        )
                        with ui.row().classes("items-center gap-2 mt-auto"):
                            def _hero_val(t=_first_urgent):
                                async def _h():
                                    hero_container.classes(add="opacity-0")
                                    await validate_review_with_feedback(t, hero_container, ["révision"], 20, 3, "moyen")
                                return _h
                            ui.button("✓ Révision faite").props(
                                "unelevated rounded color=deep-purple"
                            ).classes("text-[13px] font-semibold px-5 py-2 flex-1").on_click(
                                _hero_val()
                            )
                            ui.button("⏭ Passer").props(
                                "outline rounded color=grey"
                            ).classes("text-[13px] font-medium px-4 py-2").on_click(
                                lambda t=_first_urgent: asyncio.create_task(_on_postpone(t, hero_container, 1))
                            )

            # ── Données QCM + lacunes (batch unique) ──────────────────────────
            try:
                qcm_by_course = local_store.get_qcm_last_scores_by_course()
                lac_by_course = local_store.get_active_lacunes_count_by_course()
            except Exception:
                qcm_by_course = {}
                lac_by_course = {}

            # IU-01 — Cache QCM/lacunes pour le mode focus
            _focus_cache["qcm"] = qcm_by_course
            _focus_cache["lac"] = lac_by_course

            def _render_card(container, task, on_done, on_postpone, on_ignore):
                """Wrapper injectant qcm_info et lacune_count dans chaque carte."""
                _render_review_card(
                    container, task, on_done, on_postpone, on_ignore,
                    qcm_info=qcm_by_course.get(task.course_id),
                    lacune_count=lac_by_course.get(task.course_id, 0),
                )

            # ── Urgent ────────────────────────────────────────────────────────
            urgent_col.clear()
            shown_u = urgent[:5]
            rest_u  = urgent[5:]
            if shown_u:
                for t in shown_u:
                    _render_card(
                        urgent_col, t, _on_validate_review, _on_postpone, _on_ignore
                    )
                if rest_u:
                    _add_voir_plus(
                        urgent_col, rest_u,
                        _render_card,
                        _on_validate_review, _on_postpone, _on_ignore,
                    )
            else:
                _empty_state(urgent_col, "Aucun retard 🎉", "celebration")

            # ── Aujourd'hui ───────────────────────────────────────────────────
            today_col.clear()
            shown_t = today_tasks[:8]
            rest_t  = today_tasks[8:]
            if shown_t:
                for t in shown_t:
                    _render_card(
                        today_col, t, _on_validate_review, _on_postpone, _on_ignore
                    )
                if rest_t:
                    _add_voir_plus(
                        today_col, rest_t,
                        _render_card,
                        _on_validate_review, _on_postpone, _on_ignore,
                    )
            elif not urgent:
                # Les deux listes sont vides → CTA enrichi
                with today_col:
                    with ui.column().classes("w-full items-center py-8 gap-3 text-slate-400"):
                        ui.icon("check_circle", size="xl").classes("opacity-30")
                        ui.label("Rien à faire aujourd'hui — profites-en pour avancer !").classes(
                            "text-sm text-center font-medium"
                        )
                        with ui.row().classes("gap-2 mt-2"):
                            ui.button(
                                "Voir ma progression",
                                icon="trending_up",
                                on_click=lambda: ui.navigate.to("/stats"),
                            ).props("outline rounded size=sm color=violet")
                            ui.button(
                                "Parcourir les cours",
                                icon="business",
                                on_click=lambda: ui.navigate.to("/colleges"),
                            ).props("outline rounded size=sm color=blue-grey")
            else:
                _empty_state(today_col, "Rien de prévu aujourd'hui", "event_available")

            # ── Semaine ───────────────────────────────────────────────────────
            _rebuild_week(all_tasks)

        # ── Validation + feedback ─────────────────────────────────────────────

        async def _on_validate_review(task: ReviewTask, card):
            await validate_review_with_feedback(task, card)

        async def validate_review_with_feedback(
            task: ReviewTask,
            card,
            activity_types: list | None = None,
            duration_minutes: int | None = None,
            confidence: int | None = None,
            difficulty: str | None = None,
            qcm_result: str | None = None,
            weak_category: str | None = None,
            weak_detail: str | None = None,
        ) -> None:
            try:
                card.classes(add="ring-2 ring-green-400 bg-green-50 dark:bg-green-900/20 transition-all duration-200")
            except Exception:
                pass
            await asyncio.sleep(0.2)
            try:
                card.classes(
                    add="opacity-0 scale-95",
                    remove="ring-2 ring-green-400 bg-green-50 dark:bg-green-900/20",
                )
            except Exception:
                pass
            await asyncio.sleep(0.3)

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
            _done_today_ref["count"] += 1  # UX-06

            record_evaluation(EvaluationInput(
                source="auto_eval",
                course_id=task.course_id,
                course_title=task.course_title,
                item_number=task.item_number or "",
                context=task.context,
                activity_types=tuple(activity_types or ["révision"]),
                duration_minutes=duration_minutes,
                confidence=confidence,
                difficulty=difficulty,
                qcm_result=qcm_result,
                weak_category=weak_category,
                weak_detail=weak_detail,
            ))

            _rebuild_all()
            ui.notify(f"✓ Révisé : {task.course_title}", type="positive")

            # PP-07 — Bilan de fin de session quand toutes les urgentes sont faites
            try:
                _new_load = compute_daily_load(
                    review_service.get_urgent_tasks(
                        review_service.generate_reviews(context=_review_context, history=local_store.get_all_history())
                    ),
                    []
                )
                if _new_load["urgent_count"] == 0 and _done_today_ref["count"] >= 1:
                    _show_bilan_session(_done_today_ref["count"])
            except Exception:
                pass

            async def _sync():
                c = next((x for x in data_store.cours if x.id == task.course_id), None)
                if not c:
                    return
                if task.context == "college":
                    ok = await notion_service.increment_lecture_college(c.id, c.nb_lectures)
                    if ok:
                        c.nb_lectures += 1
                else:
                    ok = await notion_service.increment_lecture_ue(c.id, c.nb_lectures_ue)
                    if ok:
                        c.nb_lectures_ue += 1
                if ok:
                    data_store.save_to_disk()

            asyncio.create_task(_sync())

        def open_session_feedback_dialog(task: ReviewTask, card) -> None:
            """Modale 'Retour de séance' avec chips multi-sélection."""
            from types import SimpleNamespace

            if task.review_type == "bonus":
                _acts, _dur, _conf, _diff, _qcm = ["lecture"], 30, 3, "moyen", None
            elif task.review_type == "qcm_error":
                _acts, _dur, _conf, _diff, _qcm = ["qcm", "correction"], 20, 2, "difficile", "raté"
            else:
                _acts, _dur, _conf, _diff, _qcm = ["révision"], 20, 3, "moyen", None

            state = SimpleNamespace(
                activity_types=list(_acts),
                duration=_dur,
                confidence=_conf,
                difficulty=_diff,
                qcm_result=_qcm,
                weak_category=None,
                weak_detail="",
            )

            ACTIVITIES  = [("révision","Révision"),("lecture","Lecture"),("qcm","QCM"),
                           ("dp_kfp","DP/KFP"),("anki","Anki"),("fiche","Fiche"),("correction","Correction")]
            DUR_PRESETS = [5, 10, 20, 30, 45, 60, 90]
            DIFF_OPTS   = [("facile","Facile","positive"),("moyen","Moyen","warning"),("difficile","Difficile","negative")]
            QCM_OPTS    = [(None,"—","grey"),("réussi","Réussi","positive"),("moyen","Moyen","warning"),("raté","Raté","negative")]

            def _chip_on(col): return f"unelevated rounded size=sm color={col}"
            def _chip_off():   return "outline rounded size=sm color=grey"

            with ui.dialog() as dialog:
                with ui.card().classes(
                    "w-[560px] max-w-[92vw] rounded-3xl p-0 overflow-hidden "
                    "bg-white dark:bg-slate-900 shadow-2xl"
                ).style("max-height:90vh;overflow-y:auto"):

                    with ui.element("div").classes(
                        "px-6 pt-5 pb-4 border-b border-slate-100 dark:border-slate-800"
                    ):
                        with ui.row().classes("items-start justify-between w-full gap-3"):
                            with ui.column().classes("gap-0.5 min-w-0 flex-1"):
                                ui.label("Retour de séance").classes(
                                    "text-[15px] font-bold text-slate-900 dark:text-slate-50"
                                )
                                ui.label(task.label).classes(
                                    "text-xs text-slate-400"
                                ).style("overflow:hidden;white-space:nowrap;text-overflow:ellipsis")
                            ui.button(icon="close", on_click=dialog.close).props(
                                "flat round dense size=sm color=grey-7"
                            )

                    with ui.element("div").classes("px-6 py-5 flex flex-col gap-5"):

                        def _section(label: str):
                            ui.label(label).classes(
                                "text-[11px] font-bold tracking-widest text-slate-400 uppercase"
                            )

                        _section("Activités")
                        act_btns: dict[str, "ui.button"] = {}
                        with ui.row().classes("flex-wrap gap-2"):
                            for a_id, a_lbl in ACTIVITIES:
                                is_on = a_id in state.activity_types
                                b = ui.button(a_lbl).props(
                                    _chip_on("indigo") if is_on else _chip_off()
                                )
                                act_btns[a_id] = b

                        def _toggle_act(a: str):
                            if a in state.activity_types:
                                state.activity_types.remove(a)
                                act_btns[a].props(_chip_off(), remove=_chip_on("indigo"))
                            else:
                                state.activity_types.append(a)
                                act_btns[a].props(_chip_on("indigo"), remove=_chip_off())

                        for a_id, _ in ACTIVITIES:
                            act_btns[a_id].on_click(lambda a=a_id: _toggle_act(a))

                        _section("Durée")
                        dur_btns: dict[int, "ui.button"] = {}
                        with ui.row().classes("flex-wrap items-center gap-2"):
                            for d in DUR_PRESETS:
                                is_on = d == state.duration
                                b = ui.button(f"{d}′").props(
                                    _chip_on("indigo") if is_on else _chip_off()
                                )
                                dur_btns[d] = b
                            with ui.element("div").classes("flex items-center gap-1 ml-1"):
                                custom_dur = ui.number(min=1, max=300, placeholder="···").classes("w-12").props(
                                    "dense borderless"
                                )
                                ui.label("min").classes("text-xs text-slate-400 pb-0.5")

                        def _set_dur(val: int):
                            state.duration = val
                            for dv, db in dur_btns.items():
                                if dv == val:
                                    db.props(_chip_on("indigo"), remove=_chip_off())
                                else:
                                    db.props(_chip_off(), remove=_chip_on("indigo"))

                        for d in DUR_PRESETS:
                            dur_btns[d].on_click(lambda val=d: _set_dur(val))

                        def _on_custom(e):
                            if e.value:
                                state.duration = int(e.value)
                                for db in dur_btns.values():
                                    db.props(_chip_off(), remove=_chip_on("indigo"))
                        custom_dur.on_value_change(_on_custom)

                        with ui.row().classes("w-full gap-8"):
                            with ui.column().classes("gap-2"):
                                _section("Confiance")
                                _CONF_CONFIG = [
                                    (1, "😰", "red"),
                                    (2, "😟", "orange"),
                                    (3, "😐", "blue"),
                                    (4, "😊", "teal"),
                                    (5, "🔥", "green"),
                                ]
                                conf_btns: dict[int, "ui.button"] = {}
                                with ui.row().classes("gap-1.5"):
                                    for _v, _emoji, _col in _CONF_CONFIG:
                                        _is_on = _v == state.confidence
                                        _b = ui.button(_emoji).props(
                                            (_chip_on(_col) if _is_on else _chip_off()) + " round size=sm"
                                        ).tooltip(f"Confiance {_v}/5")
                                        conf_btns[_v] = _b

                                def _set_conf(val: int):
                                    state.confidence = val
                                    for v, _, col in _CONF_CONFIG:
                                        if v == val:
                                            conf_btns[v].props(_chip_on(col), remove=_chip_off())
                                        else:
                                            conf_btns[v].props(_chip_off(), remove=_chip_on(col))

                                for _v, _, _ in _CONF_CONFIG:
                                    conf_btns[_v].on_click(lambda val=_v: _set_conf(val))

                            with ui.column().classes("gap-2"):
                                _section("Difficulté")
                                diff_btns: dict[str, "ui.button"] = {}
                                with ui.row().classes("gap-1.5"):
                                    for d_id, d_lbl, d_col in DIFF_OPTS:
                                        is_on = d_id == state.difficulty
                                        b = ui.button(d_lbl).props(
                                            _chip_on(d_col) if is_on else _chip_off()
                                        )
                                        diff_btns[d_id] = b

                                def _set_diff(val: str):
                                    state.difficulty = val
                                    for d_id, _, d_col in DIFF_OPTS:
                                        if d_id == val:
                                            diff_btns[d_id].props(_chip_on(d_col), remove=_chip_off())
                                        else:
                                            diff_btns[d_id].props(_chip_off(), remove=_chip_on(d_col))

                                for d_id, _, _ in DIFF_OPTS:
                                    diff_btns[d_id].on_click(lambda val=d_id: _set_diff(val))

                        # UX-08 — Sections avancées repliées par défaut
                        with ui.expansion(
                            "Détails avancés (optionnel)",
                            value=False,
                        ).classes("w-full rounded-xl").props("dense"):
                            with ui.column().classes("gap-4 w-full pt-2"):
                                with ui.column().classes("gap-2"):
                                    _section("Résultat QCM / DP")
                                    qcm_btns: dict[str, "ui.button"] = {}
                                    with ui.row().classes("gap-1.5 flex-wrap"):
                                        for q_id, q_lbl, q_col in QCM_OPTS:
                                            is_on = q_id == state.qcm_result
                                            b = ui.button(q_lbl).props(
                                                _chip_on(q_col) if is_on else _chip_off()
                                            )
                                            qcm_btns[str(q_id)] = b

                                    def _set_qcm(val):
                                        state.qcm_result = val
                                        for q_id, _, q_col in QCM_OPTS:
                                            key = str(q_id)
                                            if q_id == val:
                                                qcm_btns[key].props(_chip_on(q_col), remove=_chip_off())
                                            else:
                                                qcm_btns[key].props(_chip_off(), remove=_chip_on(q_col))

                                    for q_id, _, _ in QCM_OPTS:
                                        qcm_btns[str(q_id)].on_click(lambda val=q_id: _set_qcm(val))

                                with ui.column().classes("gap-2"):
                                    _section("Erreur / piège EDN")
                                    _ERR_CATS = [
                                        (None,                     "—",           "grey"),
                                        ("diagnostic",             "Diagnostic",  "red"),
                                        ("clinique",               "Clinique",    "orange"),
                                        ("examens complémentaires","Examens",     "deep-orange"),
                                        ("traitement",             "Traitement",  "blue"),
                                        ("complications",          "Complic.",    "purple"),
                                        ("physiopathologie",       "Physiopath.", "indigo"),
                                        ("piège EDN",              "Piège EDN",   "pink"),
                                        ("valeur chiffrée",        "Valeur chif.","teal"),
                                        ("autre",                  "Autre",       "blue-grey"),
                                    ]
                                    cat_btns: dict[str, "ui.button"] = {}
                                    with ui.row().classes("flex-wrap gap-1.5"):
                                        for _cat_id, _cat_lbl, _cat_col in _ERR_CATS:
                                            _is_on = _cat_id == state.weak_category
                                            _b = ui.button(_cat_lbl).props(
                                                _chip_on(_cat_col) if _is_on else _chip_off()
                                            )
                                            cat_btns[str(_cat_id)] = _b

                                    def _set_cat(val):
                                        state.weak_category = val
                                        for c_id, _, c_col in _ERR_CATS:
                                            key = str(c_id)
                                            if c_id == val:
                                                cat_btns[key].props(_chip_on(c_col), remove=_chip_off())
                                            else:
                                                cat_btns[key].props(_chip_off(), remove=_chip_on(c_col))

                                    for _cat_id, _, _ in _ERR_CATS:
                                        cat_btns[str(_cat_id)].on_click(lambda val=_cat_id: _set_cat(val))

                                    ui.textarea(
                                        placeholder="Ex : oubli hémocultures avant ATB, confusion IRM avant PL…"
                                    ).classes("w-full").props("outlined dense autogrow").on_value_change(
                                        lambda e: setattr(state, "weak_detail", e.value or "")
                                    )

                    with ui.element("div").classes(
                        "px-6 py-4 bg-slate-50 dark:bg-slate-800/50 "
                        "border-t border-slate-100 dark:border-slate-800 flex justify-end gap-2"
                    ):
                        ui.button("Annuler", on_click=dialog.close).props("flat color=grey-8")

                        async def _submit():
                            dialog.close()
                            await validate_review_with_feedback(
                                task, card,
                                activity_types=state.activity_types or ["révision"],
                                duration_minutes=state.duration,
                                confidence=state.confidence,
                                difficulty=state.difficulty,
                                qcm_result=state.qcm_result,
                                weak_category=state.weak_category,
                                weak_detail=state.weak_detail or None,
                            )

                        ui.button(
                            "Valider ✓",
                            on_click=_submit,
                        ).props("unelevated color=positive rounded").classes("px-5 font-semibold")

            dialog.open()

        # ── Reporter / Ignorer ────────────────────────────────────────────────

        async def _on_postpone(task: ReviewTask, card, days: int):
            if card is not None:
                card.classes(add="opacity-0 transition-opacity duration-300")
                await asyncio.sleep(0.3)
            new_date = task.due_date + datetime.timedelta(days=days)
            local_store.postpone(
                task_id=task.id,
                course_id=task.course_id,
                context=task.context,
                review_type=task.review_type,
                theoretical_due_date=task.theoretical_due_date,
                postponed_to=new_date,
                course_title=task.course_title,
                item_number=task.item_number or "",
            )
            _rebuild_all()
            ui.notify(f"Reporté au {new_date.strftime('%d/%m')} : {task.course_title}", type="info")

        async def _on_ignore(task: ReviewTask, card):
            if card is not None:
                card.classes(add="opacity-0 transition-opacity duration-300")
                await asyncio.sleep(0.3)
            local_store.ignore(
                task_id=task.id,
                course_id=task.course_id,
                context=task.context,
                review_type=task.review_type,
                theoretical_due_date=task.theoretical_due_date,
                course_title=task.course_title,
                item_number=task.item_number or "",
            )
            _rebuild_all()
            ui.notify(f"Ignoré : {task.course_title}", type="warning")

        # ── Chargement initial ────────────────────────────────────────────────

        async def _load_all():
            _rebuild_all()

            try:
                events = (
                    data_store.dashboard_data.get("events")
                    or await calendar_service.get_events_for_day(datetime.date.today())
                )
                if agenda_col.is_deleted:
                    return
                _render_agenda(agenda_col, events)
            except Exception as exc:
                if agenda_col.is_deleted:
                    return
                logger.warning(f"Agenda load failed: {exc}")
                agenda_col.clear()
                with agenda_col:
                    with ui.column().classes("w-full items-center py-4 gap-2"):
                        ui.icon("cloud_off", size="sm").classes("text-slate-300 opacity-60")
                        ui.label("Agenda indisponible").classes("text-xs text-slate-400 italic")
                        ui.button(
                            "Réessayer",
                            on_click=lambda: ui.navigate.reload(),
                        ).props("flat dense size=xs color=grey-7").classes(
                            "text-[11px] font-medium mt-1"
                        )

        def _render_agenda(container, events: list):
            container.clear()
            today    = datetime.date.today()
            tomorrow = today + datetime.timedelta(days=1)
            days_map = {0:"Lun",1:"Mar",2:"Mer",3:"Jeu",4:"Ven",5:"Sam",6:"Dim"}

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
                        day_lbl    = "Auj."
                        line_color = "bg-violet-400"
                    elif evt_date == tomorrow:
                        day_lbl    = "Dem."
                        line_color = "bg-blue-300"
                    else:
                        day_lbl    = f"{days_map.get(evt_date.weekday(), '')} {evt_date.day}"
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

        ui.timer(0.05, _load_all, once=True)

    except Exception as e:
        logger.exception("CRITICAL DASHBOARD ERROR")
        ui.label(f"Erreur Dashboard: {e}").classes("text-red-500 font-bold")
        ui.notify(f"Erreur fatale: {e}", type="negative")


# ── Context manager colonne révision ─────────────────────────────────────────

from contextlib import contextmanager

@contextmanager
def _review_column(title: str, color: str, icon_name: str):
    """Wrapper pour une colonne de révision avec header coloré."""
    color_map = {
        "red":   ("bg-red-50 dark:bg-red-900/10",   "border-red-200 dark:border-red-800",   "text-red-600 dark:text-red-400"),
        "blue":  ("bg-blue-50 dark:bg-blue-900/10", "border-blue-200 dark:border-blue-800", "text-blue-600 dark:text-blue-400"),
        "slate": ("bg-slate-50 dark:bg-slate-800/30", "border-slate-200 dark:border-slate-700", "text-slate-500 dark:text-slate-400"),
    }
    bg, border, text = color_map.get(color, color_map["slate"])

    with ui.card().classes(
        f"w-full h-full rounded-2xl p-4 shadow-sm border {border} {bg} flex flex-col gap-3"
    ):
        with ui.row().classes("items-center gap-2 mb-1"):
            ui.icon(icon_name, size="sm").classes(text)
            ui.label(title).classes(f"font-bold text-sm {text}")
        with ui.scroll_area().classes("w-full flex-1").style("max-height: 620px;"):
            yield
