"""
semestres.py — Redirection Cockpit.
"""
from nicegui import ui
from backend.state.store import data_store
from frontend.theme import frame



def semestres_page():
    if not data_store.is_loaded:
        ui.label("Chargement des données...").classes("text-slate-500")
        return

    # ── Vue cockpit ───────────────────────────────────────────────────────────
    from frontend.pages.semestres_cockpit import render_semestres_cockpit
    render_semestres_cockpit()
    return
