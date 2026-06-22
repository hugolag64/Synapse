"""
Dashboard Synapse — Vue décisionnelle (Phase E)
------------------------------------------------
Entry point : expose `dashboard_page` pour le routeur (main.py).

Layout :
  • Bannière résumé  : N urgentes · M aujourd'hui · Xh estimé
  • Hero card (2/3)  : tâche la plus urgente
  • Focus Timer (1/3): Pomodoro compact
  • Col gauche (1/4) : Agenda + Lacune du jour
  • Col droite (3/4) : Tabs — Aujourd'hui (Urgent | Prévu) | Semaine

Architecture :
  _state.py     → DashboardState (état partagé)
  _banner.py    → context strip + stats pills
  _hero.py      → hero card
  _reviews.py   → colonnes de révision + rebuild
  _agenda.py    → agenda + lacune du jour
  _monday.py    → diagnostic lundi
  _dialogs.py   → session feedback + SR help + bilan
"""
from __future__ import annotations

import asyncio
import datetime

from nicegui import ui
from loguru import logger

from frontend.theme import frame
from frontend.components.pomodoro import PomodoroController
from backend.core.notion.service import notion_service
from backend.core.reviews import local_store
from backend.core.reviews.service import review_service
from backend.core.reviews.models import ReviewTask
from backend.core.reviews.recommendation_service import compute_daily_load
from backend.state.store import data_store

from ._state import DashboardState
from ._banner import render_banner
from ._monday import render_monday_diagnostic
from ._agenda import render_agenda_section, load_agenda
from ._reviews import render_review_columns, rebuild_all
from ._dialogs import show_bilan_session


logger.info("LOADING DASHBOARD PACKAGE")


async def dashboard_page() -> None:
    logger.info("ENTERING DASHBOARD PAGE")
    try:
        # ── State ─────────────────────────────────────────────────────────────
        state = DashboardState()
        _bilan_shown = {"shown": False}

        # ── Main layout ───────────────────────────────────────────────────────
        with ui.column().classes("w-full gap-6 max-w-7xl mx-auto"):

            # 1. Bannière + badges secondaires
            render_banner(state)

            # 2. Diagnostic du lundi (conteneur vide, rempli par timer)
            state.monday_container = ui.element("div").classes("w-full")
            ui.timer(0.1, lambda: render_monday_diagnostic(state), once=True)

            # 3. Hero card + Pomodoro
            pomo = PomodoroController()
            with ui.element("div").classes("grid grid-cols-1 lg:grid-cols-3 gap-5 w-full"):

                # Hero card (2/3)
                state.hero_container = ui.element("div").classes("lg:col-span-2 w-full")

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
                            ).props("outline rounded color=deep-purple").classes("text-[12px] font-semibold px-3")
                            ui.button(
                                f"{p2w} min", on_click=lambda w=p2w: pomo.set_mode(w)
                            ).props("outline rounded color=deep-purple").classes("text-[12px] font-semibold px-3")

                        pomo.timer = ui.timer(1.0, pomo.tick)
                        pomo.timer.deactivate()

                        ui.keyboard(
                            on_key=lambda e: pomo.toggle() if e.action.keydown and e.key.name == "Space" else None,
                            ignore=["input", "select", "textarea"],
                        )

            # 4. Grille : Agenda | Révisions
            with ui.element("div").classes("grid grid-cols-1 lg:grid-cols-4 gap-5 w-full"):

                # Col gauche : Agenda + Lacune du jour
                with ui.column().classes("col-span-1 gap-5"):
                    render_agenda_section(state)

                # Col droite : Tabs Aujourd'hui | Semaine
                with ui.element("div").classes("col-span-1 lg:col-span-3"):
                    render_review_columns(state)

        # ── Actions ───────────────────────────────────────────────────────────

        async def _on_done(
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
            state.done_today_count += 1

            local_store.add_study_session(
                course_id=task.course_id,
                course_title=task.course_title,
                item_number=task.item_number or "",
                context=task.context,
                activity_types=activity_types or ["révision"],
                duration_minutes=duration_minutes,
                confidence=confidence,
                difficulty=difficulty,
                qcm_result=qcm_result,
                weak_category=weak_category,
                weak_detail=weak_detail,
            )

            _do_rebuild()
            ui.notify(f"✓ Révisé : {task.course_title}", type="positive")

            # PP-07 — Bilan quand toutes les urgentes sont faites
            try:
                _new_load = compute_daily_load(
                    review_service.get_urgent_tasks(
                        review_service.generate_reviews(
                            context=state.review_context,
                            history=local_store.get_all_history(),
                        )
                    ),
                    [],
                )
                if _new_load["urgent_count"] == 0 and state.done_today_count >= 1 and not _bilan_shown["shown"]:
                    _bilan_shown["shown"] = True
                    show_bilan_session(state, state.done_today_count)
            except Exception:
                pass

            # Sync Notion en arrière-plan
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

        async def _on_postpone(task: ReviewTask, card, days: int) -> None:
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
            _do_rebuild()
            ui.notify(f"Reporté au {new_date.strftime('%d/%m')} : {task.course_title}", type="info")

        async def _on_ignore(task: ReviewTask, card) -> None:
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
            _do_rebuild()
            ui.notify(f"Ignoré : {task.course_title}", type="warning")

        def _do_rebuild() -> None:
            rebuild_all(state, _on_done, _on_postpone, _on_ignore, _on_done)

        # Injecter les callbacks dans le state (pour open_focus_mode)
        state.rebuild_all  = _do_rebuild
        state._on_done     = _on_done
        state._on_postpone = _on_postpone
        state._on_ignore   = _on_ignore

        # ── Chargement initial ─────────────────────────────────────────────────
        async def _load_all():
            _do_rebuild()
            await load_agenda(state)

        ui.timer(0.05, _load_all, once=True)

    except Exception as e:
        logger.exception("CRITICAL DASHBOARD ERROR")
        ui.label(f"Erreur Dashboard: {e}").classes("text-red-500 font-bold")
        ui.notify(f"Erreur fatale: {e}", type="negative")
