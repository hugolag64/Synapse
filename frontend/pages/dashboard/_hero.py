"""
_hero.py — Hero card : tâche la plus urgente.
"""
from __future__ import annotations

import asyncio

from nicegui import ui

from backend.core.reviews.models import ReviewTask
from backend.core.reviews.recommendation_service import get_next_action

from ._state import DashboardState


# ── Helpers ──────────────────────────────────────────────────────────────────

def _hero_type_key(review_type: str) -> str:
    return {
        "J3": "j3", "J7": "j7", "J14": "j14",
        "J30": "j30", "bonus": "bonus",
        "qcm_error": "qcm-error", "manuel": "manuel",
    }.get(review_type, "j14")


def _hero_urgency_label(task: ReviewTask) -> str:
    if task.days_overdue > 0:
        return f"URGENTE · +{task.days_overdue}j de retard"
    if task.review_type in ("J3", "bonus", "qcm_error"):
        return "PRIORITAIRE"
    return "Aujourd'hui"


def _hero_urgency_color(task: ReviewTask) -> str:
    if task.days_overdue > 0 or task.review_type in ("J3", "bonus", "qcm_error"):
        return "red"
    return "blue"


def render_hero(
    state: DashboardState,
    urgent: list,
    today_tasks: list,
    on_done,
    on_postpone,
    validate_fn,
) -> None:
    """Reconstruit le hero card avec la première tâche urgente (UX-01)."""
    state.hero_container.classes(remove="opacity-0")
    state.hero_container.clear()

    _first_urgent = urgent[0] if urgent else (today_tasks[0] if today_tasks else None)
    if not _first_urgent:
        # État vide : afficher un placeholder pour ne pas casser le layout
        with state.hero_container:
            with ui.element("div").classes(
                "w-full h-full synapse-hero-card flex flex-col items-center "
                "justify-center gap-3 min-h-[160px]"
            ).style("border-left-color: var(--color-j30)"):
                ui.icon("check_circle_outline", size="xl").classes("text-emerald-400 opacity-60")
                ui.label("Tout est à jour !").classes(
                    "text-[15px] font-semibold text-slate-500 dark:text-slate-400"
                )
                ui.label("Aucune révision urgente pour l'instant.").classes(
                    "text-[13px] text-slate-400 dark:text-slate-500"
                )
        return

    task: ReviewTask = _first_urgent
    border_key = _hero_type_key(task.review_type)
    urgency_label = _hero_urgency_label(task)
    urgency_color = _hero_urgency_color(task)

    # Métadonnées secondaires
    _meta_parts = []
    if task.college:
        _meta_parts.append(" · ".join(task.college[:2]))
    if task.item_number:
        _meta_parts.append(f"Item {task.item_number}")
    if task.nb_lectures > 0:
        _meta_parts.append(
            f"{task.nb_lectures} révision{'s' if task.nb_lectures > 1 else ''} effectuée{'s' if task.nb_lectures > 1 else ''}"
        )
    _meta_line = " · ".join(_meta_parts)

    # Score QCM
    try:
        from backend.core.reviews import local_store as _ls
        _qcm_scores = _ls.get_qcm_last_scores_by_course()
        _qcm_info = _qcm_scores.get(task.course_id)
        last_qcm_score: float | None = _qcm_info.get("last_score") if _qcm_info else None
        last_qcm_raw: str | None = _qcm_info.get("last_raw") if _qcm_info else None
    except Exception:
        last_qcm_score = None
        last_qcm_raw = None

    # Lacunes
    try:
        from backend.core.reviews import local_store as _ls
        _lac_counts = _ls.get_active_lacunes_count_by_course()
        _lacune_count: int = _lac_counts.get(task.course_id, 0)
    except Exception:
        _lacune_count = 0

    # Next action
    _na = get_next_action(
        task,
        last_qcm_score=last_qcm_score,
        lacune_count=_lacune_count,
    )

    with state.hero_container:
        with ui.element("div").classes(
            "w-full synapse-hero-card synapse-fade-in flex flex-col gap-4"
        ).style(
            f"border-left-color: var(--color-{border_key})"
        ):

            # ── Ligne supérieure : contexte léger ────────────────────────────
            with ui.row().classes("items-center gap-2"):
                # Dot coloré urgence
                _dot_color = "bg-red-500" if urgency_color == "red" else "bg-blue-500"
                ui.element("div").classes(
                    f"w-2 h-2 rounded-full shrink-0 {_dot_color}"
                )
                ui.label(urgency_label).classes(
                    "text-[12px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide"
                )
                ui.label("·").classes("text-slate-300 dark:text-slate-600")
                ui.label(task.type_badge).classes(
                    "text-[12px] font-semibold text-slate-400 dark:text-slate-500"
                )
                if task.college:
                    ui.label("·").classes("text-slate-300 dark:text-slate-600")
                    ui.label(task.college[0]).classes(
                        "text-[12px] text-slate-400 dark:text-slate-500 truncate"
                    )
                ui.element("div").classes("flex-1")
                # File d'attente
                _queue_total = len(urgent) + len(today_tasks)
                if _queue_total > 1:
                    with ui.element("div").classes(
                        "flex items-center gap-1 px-2 py-0.5 rounded-full "
                        "bg-slate-100 dark:bg-slate-800"
                    ):
                        ui.label(f"1/{_queue_total}").classes(
                            "text-[11px] font-bold text-slate-500 dark:text-slate-400 tabular-nums"
                        ).tooltip(f"{_queue_total} révision{'s' if _queue_total > 1 else ''} à traiter")
                if task.mastery_score is not None:
                    _m_color = {
                        "solide": "green", "correct": "blue",
                        "fragile": "orange", "critique": "red",
                    }.get(task.mastery_level or "", "slate")
                    ui.label(f"{task.mastery_score}%").classes(
                        f"text-[12px] font-semibold text-{_m_color}-500 "
                        f"dark:text-{_m_color}-400 tabular-nums"
                    ).tooltip(f"{task.mastery_level} — maîtrise globale")

            # ── Titre principal ───────────────────────────────────────────────
            ui.label(task.label).classes(
                "text-[22px] font-bold text-slate-900 dark:text-slate-50 "
                "leading-tight tracking-tight"
            )

            # ── Méta + indicateurs ────────────────────────────────────────────
            with ui.row().classes("items-center gap-3 flex-wrap"):
                if task.item_number:
                    ui.label(f"Item {task.item_number}").classes(
                        "text-[13px] text-slate-400 dark:text-slate-500"
                    )
                if task.nb_lectures > 0:
                    ui.label(f"·").classes("text-slate-300 dark:text-slate-600")
                    ui.label(
                        f"{task.nb_lectures} révision{'s' if task.nb_lectures > 1 else ''}"
                    ).classes("text-[13px] text-slate-400 dark:text-slate-500")
                if last_qcm_score is not None:
                    _qcm_color = (
                        "green" if last_qcm_score >= 70
                        else "orange" if last_qcm_score >= 55
                        else "red"
                    )
                    ui.label("·").classes("text-slate-300 dark:text-slate-600")
                    ui.label(f"QCM {last_qcm_raw or f'{last_qcm_score:.0f}%'}").classes(
                        f"text-[13px] font-semibold text-{_qcm_color}-500 "
                        f"dark:text-{_qcm_color}-400"
                    )
                if _lacune_count > 0:
                    ui.label("·").classes("text-slate-300 dark:text-slate-600")
                    ui.label(f"⚠ {_lacune_count} lacune{'s' if _lacune_count > 1 else ''}").classes(
                        "text-[13px] text-amber-500"
                    )

            # ── Recommandation ────────────────────────────────────────────────
            with ui.row().classes("items-center gap-2"):
                ui.icon(_na.icon, size="xs").classes(
                    "text-slate-400 dark:text-slate-500 shrink-0"
                )
                _na_text = _na.label
                if _na.reason:
                    _na_text += f" — {_na.reason}"
                ui.label(_na_text).classes(
                    "text-[13px] text-slate-500 dark:text-slate-400 italic flex-1 truncate"
                )
                ui.label(f"{_na.duration_min} min").classes(
                    "text-[12px] text-slate-400 dark:text-slate-500 tabular-nums shrink-0"
                )

            # ── Séparateur ────────────────────────────────────────────────────
            ui.separator().classes("opacity-30")

            # ── Boutons d'action ──────────────────────────────────────────────
            with ui.row().classes("items-center gap-2"):
                def _hero_val(t=task):
                    async def _h():
                        state.hero_container.classes(add="opacity-0")
                        await on_done(t, state.hero_container, ["révision"], 20, 3, "moyen")
                    return _h

                ui.button("Valider la révision", icon="check_circle").props(
                    "unelevated rounded color=deep-purple"
                ).classes(
                    "text-[13px] font-bold flex-1"
                ).on_click(_hero_val())

                # Reporter : menu déroulant
                with ui.element("div"):
                    _hero_postpone_btn = ui.button(
                        "Reporter", icon="skip_next"
                    ).props("flat rounded color=grey-7").classes("text-[13px]")
                    with ui.menu() as _hero_postpone_menu:
                        _hero_postpone_btn.on("click", _hero_postpone_menu.open)
                        for _days, _label in [
                            (1, "+1 jour"),
                            (3, "+3 jours"),
                            (7, "+1 semaine"),
                        ]:
                            def _make_postpone(d=_days):
                                return lambda: asyncio.create_task(
                                    on_postpone(task, state.hero_container, d)
                                )
                            ui.menu_item(_label, on_click=_make_postpone()).classes("text-xs")
