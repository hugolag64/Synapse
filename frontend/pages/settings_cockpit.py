"""settings_cockpit.py — Vue « Paramètres » cockpit (refonte, session 15).

Rendu quand preferences['ui_mode'] == 'cockpit' (early-return depuis
settings.py). Liste de connexions (Notion/Obsidian/Google Calendar = vert
connecté ; EDNpro/Hypocampus = ambre, saisie manuelle) + bascule
d'apparence clair/sombre. Le classic (Pomodoro, durées, objectif
quotidien, mode examen, LiSA/UNESS, AnythingLLM, agendas Calendar,
correspondances Obsidian, import PDF, santé du système…) reste
strictement inchangé et accessible via « Vue classic ».

Pas de capture fournie pour cet écran (absente de `screenshots/`) — mise
en page déduite du seul texte README §13.

Écarts assumés (voir Journal du CLAUDE.md de la refonte) :
  • statuts dérivés de vérifications synchrones bon marché (présence de
    fichiers/config), pas d'appel réseau live — `_check_notion` du classic
    ping l'API Notion à chaque affichage, ce qui ne convient pas à un écran
    cockpit censé s'afficher instantanément comme les autres ;
  • Notion : `settings.notion.token` est un champ Pydantic obligatoire
    (l'app ne démarre pas sans) → toujours « Connecté » ; pas un vrai
    ping live, juste un reflet du fait que l'app tourne ;
  • Obsidian / Google Calendar : mêmes vérifications que
    `frontend/pages/health.py::_check_obsidian/_check_google_calendar`
    (chemin vault configuré ; `credentials.json` + `token.json` présents),
    rejouées ici en synchrone plutôt que d'importer ces fonctions
    couplées au rendu Tailwind du classic ;
  • aucune action de connexion/déconnexion ici (le README ne décrit qu'une
    liste, pas des boutons) — configurer réellement Notion/Obsidian/
    Calendar reste classic-only.
"""
from __future__ import annotations

import os

from nicegui import ui

from backend.state.store import data_store
from backend.config.settings import settings
from frontend.pages.settings import toggle_dark_mode

_CSS = """
.se-wrap { max-width:700px; width:100%; }
.se-topbar { padding:4px 0 18px; }
.se-title { font-size:20px; font-weight:600; color:var(--text); letter-spacing:-0.01em; }
.se-subtitle { font-size:12.5px; color:var(--text-muted); margin-top:4px; }
.se-label { font-size:10px; text-transform:uppercase; letter-spacing:.04em; color:var(--text-dim); font-weight:600; margin:20px 0 8px; }
.se-list { border:1px solid var(--border); border-radius:8px; overflow:hidden; }
.se-row { display:flex; align-items:center; gap:10px; height:44px; padding:0 14px; border-bottom:1px solid var(--border); }
.se-row:last-child { border-bottom:none; }
.se-dot { width:7px; height:7px; border-radius:50%; flex:0 0 7px; }
.se-name { font-size:13px; color:var(--text); flex:1 1 auto; }
.se-status { font-size:12px; color:var(--text-muted); flex:0 0 auto; }
.se-appearance-row { display:flex; align-items:center; justify-content:space-between; gap:12px;
  border:1px solid var(--border); border-radius:8px; padding:12px 14px; }
.se-appearance-label { font-size:13px; color:var(--text); }
.se-appearance-sub { font-size:11.5px; color:var(--text-muted); margin-top:2px; }
.se-switch { width:36px; height:20px; border-radius:10px; background:var(--surface-hover); position:relative;
  cursor:pointer; flex:0 0 auto; transition: background var(--duration-base) var(--ease-standard); }
.se-switch.on { background:var(--accent); }
.se-switch-knob { position:absolute; top:2px; left:2px; width:16px; height:16px; border-radius:50%; background:var(--bg);
  transition: left var(--duration-base) var(--ease-standard); box-shadow:0 1px 2px rgba(0,0,0,0.2); }
.se-switch.on .se-switch-knob { left:18px; }
"""


def _connection_rows() -> list[tuple[str, bool | None, str]]:
    notion_ok = bool(settings.notion.token)
    obsidian_ok = bool(settings.obsidian_vault_path)
    calendar_ok = os.path.isfile("credentials.json") and os.path.isfile("token.json")

    return [
        ("Notion", notion_ok, "Connecté" if notion_ok else "Non configuré"),
        ("Obsidian", obsidian_ok, "Connecté" if obsidian_ok else "Non configuré"),
        ("Google Calendar", calendar_ok, "Connecté" if calendar_ok else "Non configuré"),
        ("EDNpro", None, "Saisie manuelle"),
        ("Hypocampus", None, "Saisie manuelle"),
    ]


def render_settings_cockpit() -> None:
    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)

    with ui.column().classes("se-wrap gap-0"):
        with ui.element("div").classes("se-topbar"):
            ui.label("Paramètres").classes("se-title")
            ui.label("Connexions · apparence").classes("se-subtitle")

        ui.label("CONNEXIONS").classes("se-label")
        with ui.element("div").classes("se-list"):
            for name, ok, status_label in _connection_rows():
                color = (
                    "var(--success)" if ok is True
                    else "var(--warning)" if ok is None
                    else "var(--text-dim)"
                )
                with ui.element("div").classes("se-row"):
                    ui.element("span").classes("se-dot").style(f"background:{color}")
                    ui.label(name).classes("se-name")
                    ui.label(status_label).classes("se-status")

        ui.label("APPARENCE").classes("se-label")
        with ui.element("div").classes("se-appearance-row"):
            with ui.column().classes("gap-0"):
                ui.label("Mode sombre").classes("se-appearance-label")
                ui.label("Basculer entre thème clair et sombre").classes("se-appearance-sub")

            is_dark = bool(data_store.preferences.get("dark_mode", False))
            switch = ui.element("div").classes("se-switch on" if is_dark else "se-switch")
            with switch:
                ui.element("div").classes("se-switch-knob")

            def _toggle(sw=switch):
                new_val = not bool(data_store.preferences.get("dark_mode", False))
                toggle_dark_mode(new_val)
                if new_val:
                    sw.classes(add="on")
                else:
                    sw.classes(remove="on")

            switch.on("click", _toggle)
