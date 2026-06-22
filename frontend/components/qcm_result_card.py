"""
qcm_result_card.py — Synapse Phase C
--------------------------------------
Carte affichant un résultat QCM (une session qcm_sessions).

Usage :
    from frontend.components.qcm_result_card import QcmResultCard
    QcmResultCard(row, on_refresh=_rebuild)
"""

from __future__ import annotations

import json
from nicegui import ui
from backend.core.reviews import local_store
from backend.core.qcm.service import (
    score_bg_classes, score_display, score_label, score_color,
    PLATFORM_BG, SESSION_TYPE_COLORS, is_failed,
)


def QcmResultCard(row, on_refresh=None):
    """
    row : sqlite3.Row issu de get_qcm_sessions_all() / get_qcm_sessions_by_course()
    on_refresh : appelé après delete
    """
    platform  = row["platform"] or "—"
    s_type    = row["session_type"] or "QCM"
    pct       = row["score_percent"]
    raw_score = row["score_raw"]
    title     = row["course_title"] or ""
    item_nb   = row["item_number"] or ""
    s_date    = (row["session_date"] or "")[:10]
    comments  = (row["comments"] or "").strip()
    sid       = row["id"]

    try:
        err_types: list = json.loads(row["error_types"] or "[]")
    except Exception:
        err_types = []

    plat_cls    = PLATFORM_BG.get(platform, "bg-slate-50 text-slate-600")
    s_type_col  = SESSION_TYPE_COLORS.get(s_type, "slate")
    score_cls   = score_bg_classes(pct)
    s_label     = score_label(pct)
    s_display   = score_display(pct, raw_score)
    failed      = is_failed(pct)

    with ui.card().classes(
        "w-full p-3 rounded-xl border border-slate-100 dark:border-slate-700 "
        "shadow-sm hover:shadow-md transition-all"
    ):
        with ui.column().classes("w-full gap-2 min-w-0"):

            # ── Ligne 1 : badges gauche + score droite ────────────────────
            with ui.row().classes("items-center gap-1.5 w-full flex-nowrap"):

                # Platform
                with ui.element("div").classes(
                    f"shrink-0 px-2 py-0.5 rounded-full text-[11px] font-bold {plat_cls}"
                ):
                    ui.label(platform)

                # Type de session
                ui.badge(s_type, color=s_type_col).classes(
                    "text-[11px] font-bold px-1.5 py-0.5 shrink-0"
                )

                ui.element("div").classes("flex-1")

                # Score (affiché à droite, prominent)
                with ui.element("div").classes(
                    f"shrink-0 flex items-center gap-1.5 px-3 py-1 rounded-full {score_cls}"
                ):
                    ui.label(s_display).classes("text-sm font-extrabold tabular-nums")
                    ui.label(f"· {s_label}").classes("text-[11px] font-semibold opacity-80")

            # ── Cours ─────────────────────────────────────────────────────
            if title:
                item_txt = f"ITEM {item_nb} — " if item_nb else ""
                ui.label(f"{item_txt}{title}").classes(
                    "text-sm font-semibold text-slate-800 dark:text-slate-100 leading-snug"
                ).style(
                    "display:-webkit-box;-webkit-line-clamp:2;"
                    "-webkit-box-orient:vertical;overflow:hidden;word-break:break-word"
                )
            else:
                ui.label("Cours non renseigné").classes("text-xs text-slate-400 italic")

            # ── Types d'erreur ────────────────────────────────────────────
            if err_types:
                with ui.row().classes("items-center gap-1.5 flex-wrap"):
                    for et in err_types:
                        ui.badge(et, color="red").classes("text-[11px] px-1.5 py-0.5")

            # ── Commentaire ───────────────────────────────────────────────
            if comments:
                ui.label(comments).classes(
                    "text-[11px] text-slate-400 leading-snug italic"
                ).style(
                    "display:-webkit-box;-webkit-line-clamp:2;"
                    "-webkit-box-orient:vertical;overflow:hidden"
                )

            # ── Footer : date + actions ───────────────────────────────────
            with ui.row().classes(
                "items-center gap-1 pt-1.5 border-t border-slate-100 dark:border-slate-700"
            ):
                ui.icon("calendar_today", size="xs").classes("text-slate-300 shrink-0")
                ui.label(s_date).classes("text-[11px] text-slate-400")

                ui.element("div").classes("flex-1")

                # Créer une lacune si raté
                if failed and row.get("course_id"):
                    def _create_lacune(r=row, sp=pct):
                        from frontend.pages.weak_points import open_add_dialog
                        from backend.core.qcm.service import suggested_severity

                        # On ouvre la page des lacunes avec le dialog pré-rempli
                        # Ici on crée directement la lacune avec les infos du QCM
                        local_store.add_weak_point_full(
                            course_id=r["course_id"],
                            detail=f"Score QCM {score_display(sp, r['score_raw'])} ({r['platform']})",
                            course_title=r["course_title"] or "",
                            item_number=r["item_number"] or "",
                            category=None,
                            severity=suggested_severity(sp),
                            source_type="qcm",
                            source_session_id=r["id"],
                        )
                        ui.notify("Lacune créée depuis ce QCM raté ✓", type="warning", icon="report_problem")
                    ui.button("+ Lacune", icon="report_problem", on_click=_create_lacune).props(
                        "flat dense size=xs color=red"
                    ).classes("text-xs").tooltip("Créer une lacune depuis ce résultat")

                # Supprimer
                def _delete(sid=sid):
                    local_store.delete_qcm_session(sid)
                    ui.notify("Résultat supprimé", type="warning")
                    if on_refresh:
                        on_refresh()

                with ui.button(icon="more_horiz").props(
                    "flat round dense size=xs"
                ).classes("text-slate-400").tooltip("Actions"):
                    with ui.menu():
                        ui.menu_item(
                            "🗑  Supprimer ce résultat", on_click=_delete
                        ).classes("text-xs text-red-400")
