"""
Dashboard Card — Synapse F-UI
------------------------------
Composant de carte de révision Clinical Black.

Usage :
    from frontend.components.dashboard_card import render_review_card

    render_review_card(
        task,
        on_done=...,      # async callable()
        on_postpone=...,  # async callable(days: int)
        on_ignore=...,    # async callable()
        qcm_info=...,     # dict | None — {last_score, last_raw}
        lacune_count=0,
    )

La carte s'insère dans le contexte NiceGUI courant.
"""
from __future__ import annotations

from typing import Callable, Optional

from nicegui import ui

from backend.core.reviews.models import ReviewTask
from backend.core.reviews.recommendation_service import get_next_action


# Couleur border-left par type de révision (CSS variable name)
_TYPE_COLOR: dict[str, str] = {
    "J3":       "j3",
    "J7":       "j7",
    "J14":      "j14",
    "J30":      "j30",
    "bonus":    "orange",
    "qcm_error":"red",
    "manuel":   "orange",
}

# Durée de base par type de révision (minutes)
_TYPE_DUR: dict[str, int] = {
    "J3": 15, "J7": 20, "J14": 25, "J30": 30,
    "bonus": 30, "qcm_error": 20, "manuel": 20,
}

# Icônes emoji confiance
_CONF_EMOJIS = [
    (1, "😰", "negative",  "Très difficile"),
    (2, "😟", "negative",  "Difficile"),
    (3, "😐", "warning",   "Moyen"),
    (4, "😊", "positive",  "Facile"),
    (5, "🔥", "positive",  "Parfait !"),
]


def render_review_card(
    task: ReviewTask,
    on_done: Optional[Callable] = None,
    on_postpone: Optional[Callable] = None,
    on_ignore: Optional[Callable] = None,
    qcm_info: Optional[dict] = None,
    lacune_count: int = 0,
) -> None:
    """
    Carte de révision Clinical Black.

    Les callbacks sont optionnels :
      on_done(confidence: int)
      on_postpone(days: int)
      on_ignore()
    """
    import datetime

    color_key = _TYPE_COLOR.get(task.review_type, "slate")
    base_dur  = _TYPE_DUR.get(task.review_type, 20)
    last_qcm_score: Optional[float] = (qcm_info or {}).get("last_score")

    # Récupérer le stage college pour la recommandation
    try:
        from backend.core.externat.service import externat_service as _ext
        _stg = _ext.get_active_stage()
        _stage_college = _stg.college_notion if _stg else None
    except Exception:
        _stage_college = None

    na = get_next_action(
        task,
        last_qcm_score=last_qcm_score,
        lacune_count=lacune_count,
        stage_college=_stage_college,
    )

    _NA_CLS: dict[str, str] = {
        "red":    "bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-300",
        "orange": "bg-orange-50 text-orange-700 dark:bg-orange-900/20 dark:text-orange-300",
        "blue":   "bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-300",
        "indigo": "bg-indigo-50 text-indigo-700 dark:bg-indigo-900/20 dark:text-indigo-300",
        "slate":  "bg-slate-50 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
    }
    na_cls = _NA_CLS.get(na.color, _NA_CLS["slate"])

    mastery_tip = ""
    if task.mastery_level:
        mastery_tip = f"{task.mastery_level.capitalize()} {task.mastery_score}%"
        if task.mastery_reasons:
            mastery_tip += " · " + " · ".join(task.mastery_reasons[:2])

    with ui.card().classes(
        "review-card w-full"
    ).style(
        f"border-left: 3px solid var(--color-{color_key}, #5E5CE6)"
    ) as card:
        with ui.column().classes("w-full gap-2 min-w-0"):

            # ── Badges ────────────────────────────────────────────────────────
            with ui.row().classes("card-header"):
                if task.item_number:
                    ui.label(f"ITEM {task.item_number}").classes("badge-item")

                ui.badge(task.type_badge, color=color_key).classes(
                    "text-[11px] font-bold px-1.5 py-0.5"
                )

                if task.context == "ue":
                    ui.badge("UE", color="teal").classes("text-[11px] px-1.5 py-0.5")

                today = datetime.date.today()
                days_future = (task.due_date - today).days
                if days_future > 0:
                    ui.badge(f"dans {days_future}j", color="blue").classes(
                        "text-[11px] px-1.5 py-0.5"
                    )

                if task.days_overdue > 0:
                    ui.label(f"+{task.days_overdue}j").classes("overdue-label")

            # ── Titre ─────────────────────────────────────────────────────────
            ui.label(task.label).classes(
                "card-title text-slate-900 dark:text-slate-100 leading-snug"
            ).style(
                "display:-webkit-box;-webkit-line-clamp:2;"
                "-webkit-box-orient:vertical;overflow:hidden"
            ).tooltip(mastery_tip or task.label)

            # ── Meta chips ────────────────────────────────────────────────────
            with ui.row().classes("card-meta"):
                if task.mastery_level:
                    _mastery_colors = {
                        "critique": "red", "fragile": "orange",
                        "en construction": "blue", "à consolider": "teal",
                        "maîtrisé": "green",
                    }
                    m_col = _mastery_colors.get(task.mastery_level, "slate")
                    ui.badge(
                        task.mastery_level.capitalize(),
                        color=m_col,
                    ).classes("text-[11px] px-1.5 py-0.5")

                if task.nb_lectures > 0:
                    ui.badge(f"{task.nb_lectures}×", color="green").classes(
                        "text-[11px] px-1.5 py-0.5 opacity-70"
                    ).tooltip(f"Lu {task.nb_lectures} fois")

                if qcm_info and last_qcm_score is not None:
                    try:
                        from backend.core.qcm.service import QCM_PASS_THRESHOLD as _thresh, score_color as _sc
                        if last_qcm_score < _thresh:
                            raw = qcm_info.get("last_raw") or f"{int(last_qcm_score)}%"
                            ui.badge(f"QCM {raw}", color=_sc(last_qcm_score)).classes(
                                "text-[11px] font-bold px-1.5 py-0.5"
                            ).tooltip(f"Dernier QCM : {raw}")
                    except Exception:
                        pass

                if lacune_count > 0:
                    ui.badge(f"⚠ {lacune_count}", color="amber").classes(
                        "text-[11px] font-bold px-1.5 py-0.5"
                    ).tooltip(f"{lacune_count} lacune(s) active(s)")

            # ── Next action ───────────────────────────────────────────────────
            with ui.row().classes(
                f"items-center gap-1.5 w-full px-2 py-1 rounded-lg {na_cls}"
            ):
                ui.icon(na.icon, size="xs").classes("shrink-0")
                ui.label(na.label).classes("text-[11px] font-bold shrink-0")
                ui.label(f"· {na.duration_min} min").classes("text-[11px] opacity-80 shrink-0")
                if na.reason:
                    ui.label(f"— {na.reason}").classes(
                        "text-[11px] opacity-60 truncate min-w-0 flex-1"
                    )

            # ── Actions ───────────────────────────────────────────────────────
            with ui.row().classes("card-actions"):

                # ── Valider (menu confiance) ──────────────────────────────────
                with ui.button(icon="check_circle").props(
                    "flat round dense size=md color=green"
                ).tooltip("D — Valider la révision"):
                    with ui.menu() as _val_menu:
                        _score_map = {
                            1: (max(base_dur, 30), "difficile"),
                            2: (max(base_dur, 25), "difficile"),
                            3: (base_dur,          "moyen"),
                            4: (min(base_dur, 15), "facile"),
                            5: (10,                "facile"),
                        }
                        with ui.element("div").classes("px-3 pt-3 pb-2 flex flex-col gap-2"):
                            ui.label("Confiance ?").classes(
                                "text-[11px] font-bold text-slate-400 uppercase tracking-wide"
                            )
                            with ui.row().classes("gap-1 justify-center mt-1"):
                                for _score, _emoji, _col, _tip in _CONF_EMOJIS:
                                    def _make_val(s=_score):
                                        async def _h():
                                            _val_menu.close()
                                            if on_done:
                                                await on_done(s)
                                        return _h
                                    ui.button(_emoji).props(
                                        f"flat round dense"
                                    ).classes(f"text-lg").on_click(
                                        _make_val(_score)
                                    ).tooltip(f"{_tip} ({_score}/5)")

                # PDF
                if task.has_pdf:
                    ui.button(
                        icon="picture_as_pdf",
                        on_click=lambda tid=task.course_id: ui.navigate.to(
                            f"/pdf/{tid}", new_tab=True
                        ),
                    ).props("flat round dense size=sm").classes(
                        "text-red-400"
                    ).tooltip("Ouvrir PDF")

                # Fiche EDN
                if task.agregation_fiche_edn:
                    ui.button(
                        icon="auto_stories",
                        on_click=lambda u=task.agregation_fiche_edn: ui.navigate.to(
                            u, new_tab=True
                        ),
                    ).props("flat round dense size=sm").classes(
                        "text-teal-400"
                    ).tooltip("Fiche EDN")

                # Voir la fiche
                ui.button(
                    icon="open_in_new",
                    on_click=lambda cid=task.course_id: ui.navigate.to(f"/cours/{cid}"),
                ).props("flat round dense size=sm").classes(
                    "text-slate-400"
                ).tooltip("Voir la fiche")

                ui.element("div").classes("flex-1")

                # Reporter / Ignorer
                if on_postpone or on_ignore:
                    with ui.button(icon="more_horiz").props(
                        "flat round dense size=sm"
                    ).classes("btn-ghost").tooltip("P — Reporter / Ignorer"):
                        with ui.menu().classes("text-sm"):
                            for days, lbl in [(1, "+1 jour"), (3, "+3 jours"), (7, "+7 jours")]:
                                def _make_post(d=days):
                                    async def _h():
                                        if on_postpone:
                                            await on_postpone(d)
                                    return _h
                                ui.menu_item(
                                    f"↻  Décaler de {lbl}",
                                    on_click=_make_post(days),
                                ).classes("text-xs")

                            ui.separator()

                            async def _do_ignore():
                                if on_ignore:
                                    await on_ignore()
                            ui.menu_item(
                                "✕  Ignorer cette révision",
                                on_click=_do_ignore,
                            ).classes("text-xs text-red-400")
