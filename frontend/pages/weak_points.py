"""
weak_points.py — Redirection Cockpit.
"""
from loguru import logger
from nicegui import ui

from backend.core.reviews import local_store
from frontend.theme import frame



def open_add_dialog(refresh_fn=None) -> None:
    """Modale simple de création manuelle d'une lacune."""
    from backend.state.store import data_store

    state = {"course_id": None, "detail": "", "category": "🛑 Rang A", "severity": 3}
    courses = getattr(data_store, "cours", []) or []

    with ui.dialog() as dlg, ui.card().classes("w-[480px] max-w-[92vw] p-5 rounded-xl"):
        ui.label("Créer une lacune").classes("text-base font-bold mb-1")
        ui.label("Rattache un point manqué ou un piège à un item.").classes("text-xs text-slate-400 mb-4")

        # Choix item
        item_opts = {c.id: f"ITEM {c.item_number or '—'} — {c.title[:30]}" for c in courses}
        if courses and not state["course_id"]:
            state["course_id"] = courses[0].id

        ui.select(options=item_opts, value=state["course_id"], label="Item concerné", on_change=lambda e: state.update({"course_id": e.value})).classes("w-full mb-3").props("outlined dense")
        
        # Choix catégorie
        ui.select(options=["🛑 Rang A", "⚠️ Piège EDN", "🔍 Diag Diff", "⏱️ Temps"], value=state["category"], label="Typologie d'erreur", on_change=lambda e: state.update({"category": e.value})).classes("w-full mb-3").props("outlined dense")

        # Détail
        ui.input(placeholder="Passage ou notion à retravailler…", on_change=lambda e: state.update({"detail": e.value})).classes("w-full mb-4").props("outlined dense autogrow rows=2")

        def _save() -> None:
            if not state["detail"].strip():
                ui.notify("Saisis une explication pour cette lacune", type="warning")
                return
            selected_course = next((c for c in courses if c.id == state["course_id"]), None)
            local_store.add_weak_point_full(
                course_id=state["course_id"] or "",
                detail=state["detail"].strip(),
                course_title=getattr(selected_course, "title", ""),
                item_number=str(getattr(selected_course, "item_number", "") or ""),
                category=state["category"],
                severity=state["severity"],
                source_type="manual",
            )
            dlg.close()
            ui.notify("Lacune créée ✓", type="positive")
            if refresh_fn:
                refresh_fn()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Annuler", on_click=dlg.close).props("flat color=grey")
            ui.button("Créer", on_click=_save).props("unelevated color=primary")

    dlg.open()


def weak_points_page(item_filter: str | None = None):
    _state = {"item": item_filter}

    with frame("Points faibles"):
        logger.info("ENTERING WEAK POINTS PAGE")

        # ── Vue cockpit ───────────────────────────────────────────────────────
        from frontend.pages.weak_points_cockpit import render_weak_points_cockpit
        render_weak_points_cockpit()
        return


