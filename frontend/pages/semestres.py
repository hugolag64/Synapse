from nicegui import ui
from frontend.theme import frame
from backend.state.store import data_store

@ui.page('/semestres')
@frame('Semestres')
def semestres_page():
    if not data_store.is_loaded:
        ui.label("Chargement des données...").classes("text-slate-500")
        return

    # ── Vue cockpit ───────────────────────────────────────────────────────────
    from frontend.pages.semestres_cockpit import render_semestres_cockpit
    render_semestres_cockpit()
    return
