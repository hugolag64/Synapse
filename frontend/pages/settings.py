"""
settings.py — Redirection Cockpit.
"""
from frontend.theme import frame


def settings_page():
    # ── Refonte : liste de connexions + apparence cockpit (feature-flag) ──────
    from frontend.pages.settings_cockpit import render_settings_cockpit
    render_settings_cockpit()
    return
