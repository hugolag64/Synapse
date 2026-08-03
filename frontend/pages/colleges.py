"""
colleges.py — Redirection Cockpit.
"""
from nicegui import ui
from backend.state.store import data_store
from frontend.theme import frame



def colleges_page():
    if not data_store.is_loaded:
        ui.label("Chargement des données…").classes("text-slate-500")
        return

    # ── Vue cockpit ───────────────────────────────────────────────────────────
    from frontend.pages.colleges_cockpit import render_colleges_cockpit
    render_colleges_cockpit()
    return
