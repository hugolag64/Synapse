"""
lisa_dialog.py — Synapse
--------------------------
Dialog OIC LiSA : affiche les Objectifs de Connaissance d'un cours
avec cases à cocher (maîtrise) et barres de progression Rang A / Rang B.

Usage :
    from frontend.components.lisa_dialog import open_lisa_dialog
    open_lisa_dialog(course)
"""
from __future__ import annotations

import asyncio
from nicegui import ui

from backend.core.reviews import local_store as ls
from backend.core.lisa.scraper import scrape_oic, LisaFetchError


def open_lisa_dialog(course) -> None:
    """Ouvre la dialog OIC pour un cours. Scrappe LiSA si pas encore en cache."""
    course_id    = course.id
    course_title = course.title or ""
    item_number  = str(getattr(course, "display_item_number", "") or "")

    with ui.dialog() as dialog, ui.card().classes(
        "w-[720px] max-w-[95vw] p-0 overflow-hidden"
    ):
        # ── Header ────────────────────────────────────────────────────────────
        with ui.element("div").classes(
            "px-5 py-4 border-b border-slate-100 dark:border-slate-700 "
            "flex items-center justify-between gap-4"
        ):
            with ui.column().classes("gap-0.5"):
                ui.label(
                    f"ITEM {item_number} — {course_title}" if item_number
                    else course_title
                ).classes("font-semibold text-sm text-slate-800 dark:text-slate-100")
                ui.label("Objectifs de connaissance LiSA").classes(
                    "text-[11px] text-slate-400"
                )

            ui.button(
                icon="refresh",
                on_click=lambda: asyncio.ensure_future(_reload()),
            ).props("flat dense round").tooltip("Actualiser depuis LiSA")

        # ── Zone de progression ───────────────────────────────────────────────
        progress_area = ui.element("div").classes(
            "px-5 pt-3 pb-2 flex flex-col gap-1.5 "
            "border-b border-slate-100 dark:border-slate-700"
        )

        # ── Zone de contenu principal ─────────────────────────────────────────
        content_area = ui.element("div").classes(
            "px-5 py-4 overflow-y-auto max-h-[60vh]"
        )

    # ── Rendu des barres de progression ──────────────────────────────────────

    def _render_progress(oics: list) -> None:
        progress_area.clear()
        with progress_area:
            rang_a = [o for o in oics if o["rang"] == "A"]
            rang_b = [o for o in oics if o["rang"] == "B"]
            mastered_a = sum(1 for o in rang_a if o["mastered"])
            mastered_b = sum(1 for o in rang_b if o["mastered"])
            total_a = len(rang_a)
            total_b = len(rang_b)

            def _bar(label: str, mastered: int, total: int, color: str) -> None:
                if total == 0:
                    return
                val = mastered / total
                with ui.row().classes("items-center gap-3 w-full"):
                    ui.label(label).classes(
                        "text-[11px] font-bold w-14 shrink-0 "
                        f"text-{color}-600 dark:text-{color}-400"
                    )
                    ui.linear_progress(value=val, color=color).classes(
                        "flex-1 h-2 rounded-full"
                    )
                    ui.label(f"{mastered}/{total}").classes(
                        "text-[11px] text-slate-500 tabular-nums w-10 text-right shrink-0"
                    )

            _bar("Rang A", mastered_a, total_a, "blue")
            _bar("Rang B", mastered_b, total_b, "violet")

    # ── Rendu des OIC ─────────────────────────────────────────────────────────

    def _render_oics(oics: list) -> None:
        _render_progress(oics)
        content_area.clear()
        with content_area:
            if not oics:
                ui.label("Aucun objectif trouvé sur LiSA pour ce cours.").classes(
                    "text-sm text-slate-400 italic py-4 text-center"
                )
                return

            rang_a = [o for o in oics if o["rang"] == "A"]
            rang_b = [o for o in oics if o["rang"] == "B"]

            with ui.row().classes("w-full gap-6 items-start"):
                for rang_label, rang_oics, color in (
                    ("Rang A", rang_a, "blue"),
                    ("Rang B", rang_b, "violet"),
                ):
                    with ui.column().classes("flex-1 gap-1 min-w-0"):
                        ui.label(rang_label).classes(
                            f"text-[11px] font-bold uppercase tracking-wider "
                            f"text-{color}-600 dark:text-{color}-400 mb-1"
                        )
                        if not rang_oics:
                            ui.label("—").classes("text-sm text-slate-300")
                            continue

                        for oic in rang_oics:
                            oic_id      = oic["id"]
                            is_mastered = bool(oic["mastered"])
                            rubrique    = oic["rubrique"] or ""

                            with ui.row().classes("items-start gap-2 py-1"):
                                def _on_toggle(e, oid=oic_id):
                                    ls.toggle_lisa_oic_mastery(oid)
                                    updated = ls.get_lisa_oic(course_id) or []
                                    _render_progress(updated)

                                cb = ui.checkbox(
                                    value=is_mastered,
                                    on_change=_on_toggle,
                                ).props("dense").classes("shrink-0 mt-0.5")

                                with ui.column().classes("gap-0.5 min-w-0"):
                                    ui.label(oic["intitule"]).classes(
                                        "text-[12px] text-slate-700 dark:text-slate-200 "
                                        "leading-snug break-words"
                                    )
                                    if rubrique:
                                        ui.badge(rubrique, color="grey").props(
                                            "outline dense"
                                        ).classes("text-[10px]")

    # ── Chargement async ──────────────────────────────────────────────────────

    async def _load(force: bool = False) -> None:
        cached = ls.get_lisa_oic(course_id)

        if cached is not None and not force:
            _render_oics(cached)
            return

        # Besoin de scrapper
        content_area.clear()
        with content_area:
            with ui.row().classes("items-center gap-3 py-6 justify-center w-full"):
                ui.spinner(size="sm")
                ui.label("Chargement depuis LiSA…").classes(
                    "text-sm text-slate-500"
                )

        try:
            oics = await asyncio.to_thread(scrape_oic, course_title, item_number)
            ls.upsert_lisa_oic(course_id, oics)
            fresh = ls.get_lisa_oic(course_id) or []
            _render_oics(fresh)
        except LisaFetchError as exc:
            content_area.clear()
            with content_area:
                ui.label(f"⚠ LiSA inaccessible : {exc}").classes(
                    "text-sm text-red-500 py-2"
                )
                ui.button(
                    "Réessayer",
                    on_click=lambda: asyncio.ensure_future(_load(True)),
                ).props("outline dense").classes("mt-2")

    async def _reload() -> None:
        await _load(force=True)

    # Lancement du chargement au prochain tick
    ui.timer(0.05, lambda: asyncio.ensure_future(_load()), once=True)
    dialog.open()
