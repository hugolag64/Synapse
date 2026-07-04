"""
_reviews.py — Colonnes de révision (Urgent / Aujourd'hui / Semaine) +
              rebuild complet + helpers.
"""
from __future__ import annotations

import datetime
from contextlib import contextmanager
from itertools import groupby

from nicegui import ui

from backend.core.reviews import local_store
from backend.core.reviews.service import review_service
from backend.core.reviews.models import ReviewTask
from backend.core.reviews.recommendation_service import get_next_action
from backend.core.reviews.mastery import PROGRESSION_COLORS
from backend.core.externat.service import externat_service

from ._state import DashboardState
from ._dialogs import (
    open_lacune_inline_dialog,
    open_session_feedback_dialog,
)


# ── Couleurs next_action ──────────────────────────────────────────────────────
_NA_COLORS = {
    "red":    "bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-300",
    "orange": "bg-orange-50 text-orange-700 dark:bg-orange-900/20 dark:text-orange-300",
    "blue":   "bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-300",
    "indigo": "bg-violet-50 text-violet-700 dark:bg-violet-900/20 dark:text-violet-300",
    "slate":  "bg-slate-50 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
}

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


# ── Render review columns (structure Morning Brief) ───────────────────────────

def render_review_columns(state: DashboardState) -> None:
    """Render la liste unifiée : section RETARD + section AUJOURD'HUI."""

    def _open_sr_help():
        from ._dialogs import open_sr_help_dialog
        open_sr_help_dialog()

    def _open_focus(_state=state):
        open_focus_mode(_state)

    with ui.element("div").classes("w-full flex flex-col gap-3"):

        # Ligne outils : filtre collège + boutons focus/aide
        with ui.row().classes("items-center gap-2"):
            state.college_filter_row = ui.row().classes(
                "flex-1 gap-1.5 flex-wrap items-center"
            )
            state.college_filter_row.set_visibility(False)
            with ui.row().classes("gap-0 shrink-0"):
                ui.button(
                    icon="center_focus_strong", on_click=_open_focus
                ).props("flat round dense size=sm").classes(
                    "text-slate-300 dark:text-slate-600"
                ).tooltip("Mode Focus — une révision à la fois")
                ui.button(icon="help_outline", on_click=_open_sr_help).props(
                    "flat round dense size=sm"
                ).classes("text-slate-300 dark:text-slate-600").tooltip("Pourquoi ces révisions ?")

        # Carte principale (liste unifiée)
        with ui.card().classes(
            "w-full rounded-2xl shadow-sm border border-slate-100 "
            "dark:border-slate-800 bg-white dark:bg-slate-900 p-0 overflow-hidden"
        ):
            # ── Section RETARD ─────────────────────────────────────────────────
            state.retard_header = ui.element("div").classes(
                "flex items-center gap-2 px-4 py-2.5 "
                "bg-red-50 dark:bg-red-950/30 "
                "border-b border-red-100 dark:border-red-900/40"
            )
            with state.retard_header:
                ui.element("div").classes(
                    "w-1.5 h-1.5 rounded-full bg-red-400 shrink-0"
                )
                ui.label("RETARD").classes(
                    "text-[11px] font-black text-red-500 dark:text-red-400 "
                    "uppercase tracking-widest flex-1"
                )
                state.urgent_count_lbl = ui.label("").classes(
                    "text-[11px] font-extrabold text-red-400 "
                    "bg-red-100 dark:bg-red-900/50 px-2 py-0.5 rounded-full tabular-nums"
                )
                state.urgent_count_lbl.set_visibility(False)
            state.retard_header.set_visibility(False)

            state.urgent_col = ui.column().classes("w-full gap-0")

            # ── Section AUJOURD'HUI ────────────────────────────────────────────
            state.today_header = ui.element("div").classes(
                "flex items-center gap-2 px-4 py-2.5 "
                "bg-slate-50 dark:bg-slate-800/30 "
                "border-t border-b border-slate-100 dark:border-slate-800"
            )
            with state.today_header:
                ui.element("div").classes(
                    "w-1.5 h-1.5 rounded-full bg-slate-300 dark:bg-slate-600 shrink-0"
                )
                ui.label("AUJOURD'HUI").classes(
                    "text-[11px] font-black text-slate-400 dark:text-slate-500 "
                    "uppercase tracking-widest flex-1"
                )
                state.today_count_lbl = ui.label("").classes(
                    "text-[11px] font-extrabold text-slate-400 "
                    "bg-slate-100 dark:bg-slate-700 px-2 py-0.5 rounded-full tabular-nums"
                )
                state.today_count_lbl.set_visibility(False)
            state.today_header.set_visibility(False)

            state.today_col = ui.column().classes("w-full gap-0")

    # week_col hors vue (backward compat)
    state.week_col = ui.element("div").classes("hidden")


# ── Context manager colonne révision ─────────────────────────────────────────

@contextmanager
def _review_column(title: str, color: str, icon_name: str):
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
        yield


# ── Render : ligne compacte Morning Brief ────────────────────────────────────

def render_review_row(
    container,
    task: ReviewTask,
    on_done=None,
    on_postpone=None,
    on_ignore=None,
    qcm_info: dict | None = None,
    lacune_count: int = 0,
    validate_fn=None,
    on_lacune_saved=None,
    is_overdue: bool = False,
):
    """Ligne compacte : [dot] [J3] [titre]  [%qcm] [⚠n] [Xmin] [✓] [⋯]"""
    col_map = {
        "J3": "blue", "J7": "indigo", "J14": "violet",
        "J30": "purple", "bonus": "orange", "qcm_error": "red", "manuel": "orange",
    }
    badge_color = col_map.get(task.review_type, "slate")
    last_qcm_score: float | None = qcm_info.get("last_score") if qcm_info else None

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

    _TYPE_DUR_BASE = {
        "J3": 15, "J7": 20, "J14": 25, "J30": 30,
        "bonus": 30, "qcm_error": 20, "manuel": 20,
    }
    _base_dur = _TYPE_DUR_BASE.get(task.review_type, 20)

    dot_cls = "bg-red-400" if is_overdue else "bg-slate-300 dark:bg-slate-600"

    with container:
        with ui.element("div").classes(
            "w-full px-4 py-3 flex items-center gap-3 "
            "border-b border-slate-50 dark:border-slate-800/50 last:border-b-0 "
            "hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors"
        ) as row_el:

            # Dot statut
            ui.element("div").classes(f"w-1.5 h-1.5 rounded-full {dot_cls} shrink-0 mt-px")

            # Badge type
            ui.badge(task.type_badge, color=badge_color).classes(
                "text-[11px] font-bold px-1.5 py-0.5 shrink-0"
            ).tooltip(f"Révision {task.review_type}")

            # Titre
            ui.label(task.label).classes(
                "flex-1 min-w-0 text-[13px] font-medium "
                "text-slate-800 dark:text-slate-100 truncate"
            )

            # Score QCM si dispo
            if last_qcm_score is not None:
                _qcm_color = (
                    "green" if last_qcm_score >= 70
                    else "orange" if last_qcm_score >= 55
                    else "red"
                )
                ui.label(f"{last_qcm_score:.0f}%").classes(
                    f"text-[11px] font-semibold text-{_qcm_color}-500 "
                    f"dark:text-{_qcm_color}-400 shrink-0 tabular-nums"
                )

            # Indicateur lacune
            if lacune_count > 0:
                ui.label(f"⚠{lacune_count}").classes(
                    "text-[11px] text-amber-500 shrink-0"
                ).tooltip(f"{lacune_count} lacune{'s' if lacune_count > 1 else ''} active{'s' if lacune_count > 1 else ''}")

            # Durée estimée
            ui.label(f"{na.duration_min}min").classes(
                "text-[11px] text-slate-300 dark:text-slate-600 shrink-0 tabular-nums"
            )

            # Bouton Valider
            def _make_val(t=task, el=row_el):
                async def _h():
                    await on_done(t, el, ["révision"], na.duration_min, 3, "moyen")
                return _h

            ui.button(icon="check_circle").props(
                "flat round dense size=sm color=green aria-label='Valider'"
            ).classes("shrink-0").on_click(_make_val()).tooltip("Valider (confiance moyenne)")

            # Menu ⋯
            with ui.button(icon="more_horiz").props(
                "flat round dense size=sm aria-label='Plus d\\'options'"
            ).classes("text-slate-300 dark:text-slate-600 shrink-0"):
                with ui.menu() as _menu:

                    # Confiance rapide
                    _CONF = [
                        (1, "😰", "Très difficile"),
                        (2, "😟", "Difficile"),
                        (3, "😐", "Moyen"),
                        (4, "😊", "Facile"),
                        (5, "🔥", "Parfait !"),
                    ]
                    _SCORE_MAP = {
                        1: (max(_base_dur, 30), "difficile"),
                        2: (max(_base_dur, 25), "difficile"),
                        3: (_base_dur,           "moyen"),
                        4: (min(_base_dur, 15),  "facile"),
                        5: (10,                  "facile"),
                    }
                    with ui.element("div").classes("px-3 pt-3 pb-2 flex flex-col gap-2"):
                        ui.label("Confiance ?").classes(
                            "text-[11px] font-bold text-slate-400 uppercase tracking-wide"
                        )
                        with ui.row().classes("gap-1 justify-center mt-1"):
                            for _sc, _em, _tip in _CONF:
                                _dur, _diff = _SCORE_MAP[_sc]
                                def _make_quick(s=_sc, d=_dur, df=_diff, t=task, el=row_el, m=_menu):
                                    async def _h():
                                        m.close()
                                        await on_done(t, el, ["révision"], d, s, df)
                                    return _h
                                ui.button(_em).props("flat round dense").classes("text-lg").on_click(
                                    _make_quick()
                                ).tooltip(f"{_tip} ({_sc}/5)")

                    ui.separator()

                    ui.menu_item(
                        "Détailler…",
                        on_click=lambda t=task, el=row_el: open_session_feedback_dialog(t, el, validate_fn),
                    ).classes("text-xs text-slate-500 font-medium")

                    ui.menu_item(
                        "Lacune…",
                        on_click=lambda t=task, r=on_lacune_saved: open_lacune_inline_dialog(t, on_save=r),
                    ).classes("text-xs text-amber-600 font-medium")

                    if task.has_pdf or task.agregation_fiche_edn:
                        ui.separator()
                        if task.has_pdf:
                            ui.menu_item(
                                "PDF",
                                on_click=lambda tid=task.course_id: ui.navigate.to(
                                    f"/pdf/{tid}", new_tab=True
                                ),
                            ).classes("text-xs")
                        if task.agregation_fiche_edn:
                            ui.menu_item(
                                "Fiche EDN",
                                on_click=lambda url=task.agregation_fiche_edn: ui.navigate.to(
                                    url, new_tab=True
                                ),
                            ).classes("text-xs")

                    if on_postpone or on_ignore:
                        ui.separator()
                        if on_postpone:
                            def _wrap_post(d, t=task, el=row_el):
                                async def _h(): await on_postpone(t, el, d)
                                return _h
                            ui.menu_item("+1 jour",    on_click=_wrap_post(1)).classes("text-xs")
                            ui.menu_item("+3 jours",   on_click=_wrap_post(3)).classes("text-xs")
                            ui.menu_item("+1 semaine", on_click=_wrap_post(7)).classes("text-xs text-amber-600")
                        if on_ignore:
                            ui.separator()
                            def _wrap_ign(t=task, el=row_el):
                                async def _h(): await on_ignore(t, el)
                                return _h
                            ui.menu_item("Ignorer", on_click=_wrap_ign()).classes("text-xs text-red-400")


# ── Voir plus (lignes) ────────────────────────────────────────────────────────

def _add_voir_plus_rows(
    container, remaining, on_done, on_postpone, on_ignore,
    qcm_by_course, lac_by_course, on_lacune_saved, validate_fn, is_overdue,
):
    with container:
        extra_col = ui.column().classes("w-full gap-0")
    extra_col.set_visibility(False)

    for t in remaining:
        render_review_row(
            extra_col, t, on_done, on_postpone, on_ignore,
            qcm_info=qcm_by_course.get(t.course_id),
            lacune_count=lac_by_course.get(t.course_id, 0),
            on_lacune_saved=on_lacune_saved,
            validate_fn=validate_fn,
            is_overdue=is_overdue,
        )

    n = len(remaining)
    with container:
        btn = ui.button(f"Voir {n} de plus ↓").props(
            "flat dense size=sm color=blue-grey"
        ).classes("w-full text-[11px] py-2")

        def _toggle(b=btn, ec=extra_col):
            vis = not ec.visible
            ec.set_visibility(vis)
            b.set_text("Masquer ↑" if vis else f"Voir {n} de plus ↓")

        btn.on_click(_toggle)


# ── État vide ─────────────────────────────────────────────────────────────────

def _empty_state(container, message: str, icon_name: str = "check_circle", action_label=None, action_fn=None):
    with container:
        with ui.column().classes("w-full items-center py-6 gap-2 text-slate-400"):
            ui.icon(icon_name, size="lg").classes("opacity-40")
            ui.label(message).classes("text-xs text-center font-medium")
            if action_label and action_fn:
                ui.button(action_label, on_click=action_fn).props(
                    "flat dense size=sm color=violet"
                ).classes("text-[11px] font-semibold mt-1")


# ── Voir plus ─────────────────────────────────────────────────────────────────

def _add_voir_plus(container, remaining, render_fn, on_validate, on_postpone, on_ignore):
    with container:
        extra_col = ui.column().classes("w-full gap-2")
    extra_col.set_visibility(False)

    for t in remaining:
        render_fn(extra_col, t, on_validate, on_postpone, on_ignore)

    with container:
        btn = ui.button(
            f"Voir {len(remaining)} de plus ↓"
        ).props("flat dense size=sm color=blue-grey").classes("w-full text-xs mt-1")

        def _toggle(b=btn, ec=extra_col, rem=remaining):
            vis = not ec.visible
            ec.set_visibility(vis)
            b.set_text("Masquer ↑" if vis else f"Voir {len(rem)} de plus ↓")

        btn.on_click(_toggle)


# ── Helpers type key ────────────────────────────────────────────────────────

def _type_key(review_type: str) -> str:
    """Retourne la clé CSS var(--color-<key>) correspondant au review_type."""
    return {
        "J3": "j3", "J7": "j7", "J14": "j14",
        "J30": "j30", "bonus": "bonus",
        "qcm_error": "qcm-error", "manuel": "manuel",
    }.get(review_type, "j14")


# ── Render : carte révision ───────────────────────────────────────────────────

def render_review_card(
    container,
    task: ReviewTask,
    on_done=None,
    on_postpone=None,
    on_ignore=None,
    qcm_info: dict | None = None,
    lacune_count: int = 0,
    validate_fn=None,
    on_lacune_saved=None,
):
    """Carte de révision redessinée — bordure colorée, mini QCM bar, next_action pill."""
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
        "notion": "Date Notion (planification manuelle)",
        "sm2":    "Date SM-2 (intervalle adaptatif)",
        "fixe":   "Date fixe (J+offset théorique)",
    }
    _type_tip = _REVIEW_TYPE_TIPS.get(task.review_type, task.review_type)
    if task.date_source:
        _type_tip += f"\n{_DATE_SOURCE_LABELS.get(task.date_source, task.date_source)}"

    last_qcm_score: float | None = None
    if qcm_info:
        last_qcm_score = qcm_info.get("last_score")

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

    mastery_tip = ""
    if task.mastery_level:
        mastery_tip = f"{task.mastery_level.capitalize()} {task.mastery_score}%"
        if task.mastery_reasons:
            mastery_tip += " · " + " · ".join(task.mastery_reasons[:2])

    lec = task.nb_lectures
    border_color_key = _type_key(task.review_type)

    # Ligne secondaire collège + item + lectures
    _meta_parts = []
    if task.college:
        _meta_parts.append(" · ".join(task.college[:2]))
    if task.item_number:
        _meta_parts.append(f"Item {task.item_number}")
    if lec > 0:
        _meta_parts.append(f"{lec} lecture{'s' if lec > 1 else ''}")
    _meta_line = " · ".join(_meta_parts)

    _tstate = {"t0": None}

    with container:
        with ui.element("div").classes(
            "review-card w-full synapse-fade-in"
        ).style(
            f"border-left-color: var(--color-{border_color_key})"
        ) as card:
            with ui.column().classes("w-full gap-1 min-w-0"):

                # ── Ligne 1 : titre + indicateurs droite ──────────────────────
                with ui.row().classes("items-start gap-2 min-w-0 w-full"):
                    ui.label(task.label).classes(
                        "text-[14px] font-medium text-slate-800 dark:text-slate-100 "
                        "flex-1 min-w-0 leading-snug"
                    ).style(
                        "display:-webkit-box;-webkit-line-clamp:2;"
                        "-webkit-box-orient:vertical;overflow:hidden"
                    ).tooltip(mastery_tip or task.label)
                    with ui.row().classes("items-center gap-2 shrink-0 mt-0.5"):
                        if last_qcm_score is not None:
                            _qcm_color = (
                                "green" if last_qcm_score >= 70
                                else "orange" if last_qcm_score >= 55
                                else "red"
                            )
                            ui.label(f"{last_qcm_score:.0f}%").classes(
                                f"text-[12px] font-semibold text-{_qcm_color}-500 "
                                f"dark:text-{_qcm_color}-400 tabular-nums"
                            )
                        if lacune_count > 0:
                            ui.label(f"⚠ {lacune_count}").classes(
                                "text-[12px] text-amber-500"
                            ).tooltip(f"{lacune_count} lacune{'s' if lacune_count > 1 else ''} active{'s' if lacune_count > 1 else ''}")

                # ── Ligne 2 : meta + durée recommandée ────────────────────────
                with ui.row().classes("items-center gap-1 w-full min-w-0"):
                    if _meta_line:
                        ui.label(_meta_line).classes(
                            "text-[12px] text-slate-400 dark:text-slate-500 truncate flex-1 min-w-0"
                        )
                    else:
                        ui.element("div").classes("flex-1")
                    with ui.row().classes("items-center gap-1 shrink-0"):
                        ui.icon(na.icon, size="xs").classes("text-slate-300 dark:text-slate-600")
                        ui.label(f"{na.duration_min} min").classes(
                            "text-[11px] text-slate-400 dark:text-slate-500 tabular-nums"
                        ).tooltip(f"{na.label}{' — ' + na.reason if na.reason else ''}")

                # ── Actions ───────────────────────────────────────────────────

                with ui.row().classes(
                    "w-full items-center gap-1 pt-1 border-t "
                    "border-slate-50 dark:border-slate-800/60"
                ):
                    _tel = ui.label("").classes(
                        "text-[11px] font-mono text-orange-500 dark:text-orange-400 shrink-0"
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

                    ui.button("⏱").props("flat round dense size=xs").classes(
                        "text-slate-300 hover:text-orange-500 shrink-0"
                    ).tooltip("Chronométrer (auto-remplit la durée)").on_click(_toggle_timer)

                    # UX-02 — Bouton 1-clic "✓ Valider"
                    def _make_direct_val(t, c, _ts=_tstate):
                        async def _h():
                            _dur = 20
                            if _ts["t0"] is not None:
                                _dur = max(1, int(
                                    (datetime.datetime.now() - _ts["t0"]).total_seconds() / 60
                                ))
                            await on_done(t, c, ["révision"], _dur, 3, "moyen")
                        return _h

                    ui.button("Valider").props(
                        "unelevated rounded dense size=sm color=green-6"
                        " aria-label='Valider la révision'"
                    ).classes("text-[11px] font-bold px-3").on_click(
                        _make_direct_val(task, card)
                    ).tooltip("Valider rapidement (confiance moyenne)")

                    with ui.button(icon="tune").props(
                        "flat round dense size=sm color=green aria-label='Feedback détaillé'"
                    ).tooltip("Valider avec feedback détaillé"):
                        with ui.menu() as _val_menu:
                            _CONF_EMOJIS = [
                                (1, "😰", "red",   "Très difficile"),
                                (2, "😟", "orange","Difficile"),
                                (3, "😐", "blue",  "Moyen"),
                                (4, "😊", "teal",  "Facile"),
                                (5, "🔥", "green", "Parfait !"),
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
                                    await on_done(t, c, ["révision"], _dur, score, _diff)
                                return _h

                            with ui.element("div").classes("px-3 pt-3 pb-2 flex flex-col gap-2"):
                                ui.label("Confiance ?").classes(
                                    "text-[11px] font-bold text-slate-400 uppercase tracking-wide"
                                )
                                with ui.row().classes("gap-1 justify-center mt-1"):
                                    for _score, _emoji, _col, _tip in _CONF_EMOJIS:
                                        ui.button(_emoji).props("flat round dense").classes(
                                            f"text-lg text-{_col}-500 hover:bg-{_col}-50 dark:hover:bg-slate-700"
                                        ).on_click(
                                            _make_quick_val(_score, task, card, _val_menu, _base_dur)
                                        ).tooltip(f"{_tip} ({_score}/5)")

                            ui.separator().classes("mb-1")
                            ui.menu_item(
                                "Détailler...",
                                on_click=lambda t=task, c=card: open_session_feedback_dialog(
                                    t, c, validate_fn
                                ),
                            ).classes("text-xs text-slate-500 font-medium")
                            ui.separator()
                            ui.menu_item(
                                "Lacune...",
                                on_click=lambda t=task, r=on_lacune_saved: open_lacune_inline_dialog(t, on_save=r),
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

                    # IU-06 — ui.timer de tick
                    def _tick_fn(_ts=_tstate, _lbl=_tel):
                        if _ts["t0"]:
                            _e = int((datetime.datetime.now() - _ts["t0"]).total_seconds())
                            _m, _s = divmod(_e, 60)
                            _lbl.set_text(f"{_m:02d}:{_s:02d}")
                    _ctmr = ui.timer(1.0, _tick_fn)
                    _ctmr.deactivate()

                    # ── Reporter (menu déroulant) + Ignorer ───────────────────
                    if on_postpone or on_ignore:
                        def wrap_post(t, c, d):
                            async def _h(): await on_postpone(t, c, d)
                            return _h
                        def wrap_ign(t, c):
                            async def _h(): await on_ignore(t, c)
                            return _h

                        with ui.element("div"):
                            _postpone_btn = ui.button(icon="skip_next").props(
                                "flat round dense size=xs color=grey-7"
                            ).tooltip("Reporter")
                            with ui.menu() as _postpone_menu:
                                _postpone_btn.on("click", _postpone_menu.open)
                                ui.menu_item(
                                    "+1 jour",
                                    on_click=wrap_post(task, card, 1),
                                ).classes("text-xs")
                                ui.menu_item(
                                    "+3 jours",
                                    on_click=wrap_post(task, card, 3),
                                ).classes("text-xs")
                                ui.menu_item(
                                    "+1 semaine",
                                    on_click=wrap_post(task, card, 7),
                                ).classes("text-xs text-amber-600").tooltip(
                                    "Peut créer un retard critique"
                                )

                        ui.button(icon="close").props(
                            "flat round dense size=xs color=grey-7"
                        ).classes(
                            "opacity-50 hover:opacity-100 transition-opacity"
                        ).tooltip("Ignorer cette révision").on_click(
                            wrap_ign(task, card)
                        )


# ── Render : ligne compacte (vue Semaine) ─────────────────────────────────────

def render_task_row(
    container,
    task: ReviewTask,
    on_done=None,
    on_postpone=None,
    on_ignore=None,
    validate_fn=None,
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
        async def _h(): await on_done(t, el, a, dur, conf, diff)
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
            ui.badge(task.type_badge, color=badge_color).classes(
                "text-[11px] font-bold px-1.5 py-0.5 shrink-0"
            ).tooltip(_type_tip_row)

            if task.mastery_level in ("critique", "fragile"):
                m_color = PROGRESSION_COLORS.get(task.mastery_level, "slate")
                ui.badge(task.mastery_level.capitalize(), color=m_color).classes(
                    "text-[11px] px-1 py-0.5 shrink-0"
                )

            ui.label(task.label).classes(
                "text-sm text-slate-700 dark:text-slate-200 flex-1 min-w-0 font-medium truncate"
            ).tooltip(task.course_title)

            ui.label(f"{na.duration_min}min").classes(
                "text-[11px] text-slate-400 shrink-0 tabular-nums"
            )

            ui.button(
                icon="check_circle",
                on_click=_wrap_val(task, row_el, ["révision"], 20, 3, "moyen"),
            ).props("flat round dense size=md color=green").classes("shrink-0").tooltip("Valider (20min · conf.3)")

            with ui.button(icon="more_horiz").props("flat round dense size=sm").classes("text-slate-400 shrink-0"):
                with ui.menu().classes("text-sm"):
                    ui.menu_item("⚡  Rapide — 10min",   on_click=_wrap_val(task, row_el, ["révision"], 10, 4, "facile")).classes("text-xs")
                    ui.menu_item("💪  Difficile — 30min", on_click=_wrap_val(task, row_el, ["révision"], 30, 2, "difficile")).classes("text-xs")
                    ui.menu_item(
                        "🔍  Détailler…",
                        on_click=lambda t=task, el=row_el: open_session_feedback_dialog(t, el, validate_fn),
                    ).classes("text-xs")
                    ui.separator()
                    ui.menu_item("↻  Décaler +1j", on_click=_wrap_post(task, row_el, 1)).classes("text-xs")
                    ui.menu_item("↻  Décaler +3j", on_click=_wrap_post(task, row_el, 3)).classes("text-xs")
                    ui.menu_item("↻  Décaler +7j", on_click=_wrap_post(task, row_el, 7)).classes("text-xs")
                    ui.separator()
                    ui.menu_item("✕  Ignorer", on_click=_wrap_ign(task, row_el)).classes("text-xs text-red-400")


# ── Rebuild semaine ───────────────────────────────────────────────────────────

def rebuild_week(state: DashboardState, all_tasks: list, on_done, on_postpone, on_ignore, validate_fn) -> None:
    state.week_col.clear()
    pool = (
        review_service.get_today_tasks(all_tasks) +
        review_service.get_upcoming_tasks(all_tasks, days=7)
    )
    if not pool:
        _empty_state(state.week_col, "Aucune révision cette semaine", "event_available")
        return
    pool_sorted = sorted(pool, key=lambda t: t.due_date)
    for day_date, group in groupby(pool_sorted, key=lambda t: t.due_date):
        tasks_day = list(group)
        with state.week_col:
            with ui.row().classes("items-center gap-2 px-2 pt-3 pb-0.5"):
                ui.label(_day_label(day_date)).classes(
                    "text-[11px] font-bold uppercase tracking-wide text-slate-400 dark:text-slate-500 flex-1"
                )
                ui.badge(str(len(tasks_day)), color="slate").classes("text-[11px]")
            ui.separator().classes("mb-0.5 opacity-50")
        for t in tasks_day:
            render_task_row(state.week_col, t, on_done, on_postpone, on_ignore, validate_fn)


# ── Render filtre collège ─────────────────────────────────────────────────────

def render_college_chips(state: DashboardState, all_tasks: list) -> None:
    state.college_filter_row.clear()
    state.college_chip_refs.clear()
    colleges_in_tasks = sorted({
        cg for t in all_tasks for cg in (t.college or [])
    })
    if len(colleges_in_tasks) <= 1:
        state.college_filter_row.set_visibility(False)
        return
    state.college_filter_row.set_visibility(True)
    with state.college_filter_row:
        ui.label("Filtre :").classes(
            "text-[11px] font-bold text-slate-400 uppercase tracking-wide shrink-0"
        )
        active_col = state.college_filter

        def _make_chip(label, college_val):
            is_active = (college_val == active_col)
            btn = ui.button(label).props(
                f"{'unelevated' if is_active else 'outline'} rounded dense size=xs "
                f"color={'violet' if is_active else 'grey'}"
            ).classes("text-[11px] font-semibold")
            def _on_click(v=college_val):
                state.college_filter = None if state.college_filter == v else v
                if state.rebuild_all:
                    state.rebuild_all()
            btn.on_click(_on_click)
            return btn

        _make_chip("Tout", None)
        for cg in colleges_in_tasks:
            _make_chip(cg, cg)


# ── Rebuild complet ───────────────────────────────────────────────────────────

def rebuild_all(
    state: DashboardState,
    on_done,
    on_postpone,
    on_ignore,
    validate_fn,
) -> None:
    """Reconstruit toutes les colonnes de révision + bannière."""
    from ._banner import update_banner

    history   = local_store.get_all_history()
    all_tasks = review_service.generate_reviews(
        context=state.review_context, history=history
    )
    all_tasks = externat_service.apply_stage_boost(all_tasks)

    render_college_chips(state, all_tasks)
    if state.college_filter:
        all_tasks = [
            t for t in all_tasks
            if state.college_filter in (t.college or [])
        ]

    urgent      = review_service.get_urgent_tasks(all_tasks)
    today_tasks = review_service.get_today_tasks(all_tasks)

    state.focus_tasks = urgent + today_tasks

    # UX-10 — Comptage révisions cette semaine
    _week_ago = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    _week_count = sum(
        1 for h in history
        if getattr(h, "done_date", None) and str(getattr(h, "done_date", "")) >= _week_ago
    )

    # Bannière
    from backend.core.reviews.recommendation_service import compute_daily_load
    load = compute_daily_load(urgent, today_tasks)
    update_banner(state, load, done_today=state.done_today_count, week_count=_week_count)

    # QCM + lacunes (batch)
    try:
        qcm_by_course = local_store.get_qcm_last_scores_by_course()
        lac_by_course = local_store.get_active_lacunes_count_by_course()
    except Exception:
        qcm_by_course = {}
        lac_by_course = {}

    state.focus_cache["qcm"] = qcm_by_course
    state.focus_cache["lac"] = lac_by_course

    def _render_row(container, task, _is_overdue):
        render_review_row(
            container, task, on_done, on_postpone, on_ignore,
            qcm_info=qcm_by_course.get(task.course_id),
            lacune_count=lac_by_course.get(task.course_id, 0),
            on_lacune_saved=state.rebuild_all,
            validate_fn=validate_fn,
            is_overdue=_is_overdue,
        )

    # Section RETARD
    has_urgent = bool(urgent)
    if state.retard_header is not None:
        state.retard_header.set_visibility(has_urgent)
    if state.urgent_count_lbl is not None:
        state.urgent_count_lbl.set_text(str(len(urgent)))
        state.urgent_count_lbl.set_visibility(has_urgent)

    state.urgent_col.clear()
    if urgent:
        shown_u = urgent[:5]
        rest_u  = urgent[5:]
        for t in shown_u:
            _render_row(state.urgent_col, t, True)
        if rest_u:
            _add_voir_plus_rows(
                state.urgent_col, rest_u, on_done, on_postpone, on_ignore,
                qcm_by_course, lac_by_course, state.rebuild_all, validate_fn, True,
            )

    # Section AUJOURD'HUI
    has_today = bool(today_tasks)
    if state.today_header is not None:
        state.today_header.set_visibility(has_today or not urgent)
    if state.today_count_lbl is not None:
        state.today_count_lbl.set_text(str(len(today_tasks)))
        state.today_count_lbl.set_visibility(has_today)

    state.today_col.clear()
    if today_tasks:
        shown_t = today_tasks[:8]
        rest_t  = today_tasks[8:]
        for t in shown_t:
            _render_row(state.today_col, t, False)
        if rest_t:
            _add_voir_plus_rows(
                state.today_col, rest_t, on_done, on_postpone, on_ignore,
                qcm_by_course, lac_by_course, state.rebuild_all, validate_fn, False,
            )
    elif not urgent:
        # Rien du tout — état vide global
        if state.today_header is not None:
            state.today_header.set_visibility(False)
        with state.today_col:
            with ui.column().classes("w-full items-center py-10 gap-3 text-slate-400 px-4"):
                ui.icon("check_circle", size="xl").classes("opacity-30")
                ui.label("Rien à faire aujourd'hui — profites-en pour avancer !").classes(
                    "text-sm text-center font-medium"
                )
                with ui.row().classes("gap-2 mt-2"):
                    ui.button(
                        "Ma progression",
                        icon="trending_up",
                        on_click=lambda: ui.navigate.to("/stats"),
                    ).props("outline rounded size=sm color=violet")
                    ui.button(
                        "Parcourir les cours",
                        icon="business",
                        on_click=lambda: ui.navigate.to("/colleges"),
                    ).props("outline rounded size=sm color=blue-grey")

    # Semaine
    rebuild_week(state, all_tasks, on_done, on_postpone, on_ignore, validate_fn)


# ── Mode Focus ────────────────────────────────────────────────────────────────

def open_focus_mode(state: DashboardState) -> None:
    """Dialog mode focus — une révision à la fois.

    Récupère les callbacks on_done / on_postpone / on_ignore depuis state.rebuild_all
    (qui est injecté par __init__.py). Pour la validation il faut passer par le
    validate_fn stocké dans state via un attribut dédié.
    """
    tasks = list(state.focus_tasks)
    if not tasks:
        ui.notify("Aucune révision à faire !", type="info")
        return

    # Récupérer les callbacks depuis state (injectés par __init__.py)
    _on_done      = getattr(state, "_on_done",     None)
    _on_postpone  = getattr(state, "_on_postpone", None)
    _on_ignore    = getattr(state, "_on_ignore",   None)

    _idx = {"i": 0}

    with ui.dialog(value=True).props("maximized persistent") as _fdlg, \
         ui.card().classes(
             "w-full h-full max-w-none rounded-none p-0 "
             "bg-slate-50 dark:bg-slate-950 flex flex-col overflow-hidden"
         ):
        with ui.row().classes(
            "w-full items-center gap-3 px-6 py-3 shrink-0 "
            "border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900"
        ):
            ui.icon("center_focus_strong").classes("text-violet-500")
            ui.label("Mode Focus").classes(
                "text-base font-bold text-slate-900 dark:text-slate-100 flex-1"
            )
            _ctr = ui.label("").classes(
                "text-sm font-mono text-slate-500 px-2 py-0.5 bg-slate-100 dark:bg-slate-800 rounded-full"
            )
            ui.button(icon="close", on_click=_fdlg.close).props(
                "flat round dense size=sm color=grey-7"
            ).tooltip("Quitter le mode focus")

        with ui.scroll_area().classes("flex-1"):
            with ui.element("div").classes("w-full max-w-lg mx-auto p-6"):
                _focus_col = ui.column().classes("w-full gap-3")

        with ui.row().classes(
            "w-full items-center justify-between px-6 py-3 shrink-0 "
            "border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900"
        ):
            _prev_btn = ui.button("← Précédent").props("outline rounded size=sm color=slate").on_click(
                lambda: _nav(-1)
            )
            ui.button("Fermer", on_click=_fdlg.close).props("flat rounded size=sm color=grey")
            _next_btn = ui.button("Suivant →").props("unelevated rounded size=sm color=violet").on_click(
                lambda: _nav(1)
            )

    def _render_focus():
        _focus_col.clear()
        t = tasks[_idx["i"]]
        _ctr.set_text(f"{_idx['i'] + 1} / {len(tasks)}")
        _prev_btn.set_enabled(_idx["i"] > 0)
        _next_btn.set_enabled(_idx["i"] < len(tasks) - 1)
        render_review_card(
            _focus_col, t,
            on_done=_focus_on_done,
            on_postpone=_focus_on_postpone,
            on_ignore=_focus_on_ignore,
            qcm_info=state.focus_cache["qcm"].get(t.course_id),
            lacune_count=state.focus_cache["lac"].get(t.course_id, 0),
            validate_fn=_on_done,
            on_lacune_saved=state.rebuild_all,
        )

    async def _focus_on_done(task, card, activity_types=None, duration_minutes=None, confidence=None, difficulty=None, **kwargs):
        if _on_done:
            await _on_done(task, card, activity_types, duration_minutes, confidence, difficulty)
        _nav(1)

    async def _focus_on_postpone(task, card, days):
        if _on_postpone:
            await _on_postpone(task, card, days)
        _nav(1)

    async def _focus_on_ignore(task, card):
        if _on_ignore:
            await _on_ignore(task, card)
        _nav(1)

    def _nav(delta: int):
        ni = _idx["i"] + delta
        if 0 <= ni < len(tasks):
            _idx["i"] = ni
            _render_focus()
        elif ni >= len(tasks):
            _fdlg.close()
            ui.notify("✓ Focus terminé — toutes les révisions traitées !", type="positive")

    _render_focus()
