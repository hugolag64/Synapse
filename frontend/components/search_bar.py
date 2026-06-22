"""
search_bar.py — Synapse
-----------------------
Barre de recherche fuzzy médicale (composant NiceGUI standalone).

Usage :
    from frontend.components.search_bar import render_instant_search

    render_instant_search(on_select=lambda course: ui.navigate.to(f"/cours/{course.id}"))
"""
from __future__ import annotations

from typing import Callable, Optional

from nicegui import ui

from backend.core.search.service import search_index


def render_instant_search(
    on_select: Optional[Callable] = None,
    placeholder: str = "/ Rechercher un cours, ITEM, collège…",
    limit: int = 8,
) -> None:
    """
    Affiche un input fuzzy + liste de résultats dans le contexte NiceGUI courant.
    on_select(cours) est appelé au clic sur un résultat.
    """
    results_col = ui.column().classes("w-full gap-0 mt-1")

    def _on_search(e):
        q = (e.value or "").strip()
        results_col.clear()

        if len(q) < 2:
            return

        hits = search_index.search(q, limit=limit)
        if not hits:
            with results_col:
                ui.label("Aucun résultat").classes(
                    "text-xs text-slate-400 italic px-3 py-2"
                )
            return

        with results_col:
            for cours, score in hits:
                def _pick(c=cours):
                    results_col.clear()
                    if on_select:
                        on_select(c)

                item_txt = f"ITEM {cours.display_item_number} — " if cours.display_item_number else ""
                college_txt = ", ".join((cours.college or [])[:2])

                with ui.element("div").classes(
                    "w-full px-3 py-2 flex items-center gap-3 cursor-pointer rounded "
                    "hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                ).on("click", _pick):
                    with ui.column().classes("flex-1 gap-0 min-w-0"):
                        ui.label(f"{item_txt}{cours.title}").classes(
                            "text-sm font-semibold text-slate-800 dark:text-slate-100 truncate"
                        )
                        if college_txt:
                            ui.label(college_txt).classes(
                                "text-[11px] text-slate-400 truncate"
                            )
                    ui.badge(f"{score}%", color="blue").classes(
                        "text-[11px] shrink-0 opacity-60"
                    )

    ui.input(
        placeholder=placeholder,
        on_change=_on_search,
    ).props("autofocus clearable outlined dense").classes("w-full text-sm")
