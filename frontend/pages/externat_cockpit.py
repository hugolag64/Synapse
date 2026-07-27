"""externat_cockpit.py — Vue « Externat » cockpit (refonte, session 14).

Rendu quand preferences['ui_mode'] == 'cockpit' (early-return depuis
externat.py). Cartes de stage clinique : nom, statut, dates, items
rattachés. Écran purement visuel — le README §12 ne décrit qu'une liste de
cartes, pas d'action ; le classic garde la gestion complète (créer/éditer/
supprimer un stage, cours/lacunes/QCM du stage) accessible via
« Vue classic ».

Écarts assumés (voir Journal du CLAUDE.md de la refonte) :
  • pas de champ « lieu » dans `Stage` (seulement `specialty`) — la capture
    montre « Cardiologie · CHU » mais aucun second champ n'existe côté
    backend pour ce « CHU » ; titre = `stage.specialty` seul plutôt que
    d'inventer un lieu ;
  • couleurs de statut cockpit ≠ `Stage.status_color` classic (qui donne
    vert à « En cours », gris à « Terminé ») — la capture veut l'inverse
    (ambre = en cours, vert = terminé), cohérent avec la grammaire de
    statut déjà utilisée ailleurs (vert = fait/résolu, ambre = en cours) ;
    mapping cockpit dédié, `Stage.status_color` non touché ;
  • « Items rattachés » = `externat_service.get_stage_courses(stage)`
    (cours du collège du stage), items avec un `item_number`, 6 premiers
    affichés + compteur « +N » si plus.
"""
from __future__ import annotations

import datetime

from nicegui import ui

from backend.core.externat import store as externat_store
from backend.core.externat.service import externat_service

_MONTHS_FR = ["jan", "fév", "mar", "avr", "mai", "juin",
              "juil", "août", "sep", "oct", "nov", "déc"]

_STATUS_COLOR = {
    "En cours": "var(--warning)",
    "À venir": "var(--text-dim)",
    "Terminé": "var(--success)",
}

_CSS = """
.ex-wrap { max-width:900px; width:100%; }
.ex-topbar { padding:4px 0 18px; }
.ex-title { font-size:20px; font-weight:600; color:var(--text); letter-spacing:-0.01em; }
.ex-subtitle { font-size:12.5px; color:var(--text-muted); margin-top:4px; }
.ex-list { display:flex; flex-direction:column; gap:12px; width:100%; }
.ex-card { border:1px solid var(--border); border-radius:8px; padding:16px 18px; }
.ex-card-head { display:flex; align-items:baseline; justify-content:space-between; gap:12px; }
.ex-card-title { font-size:14.5px; font-weight:600; color:var(--text); }
.ex-status { display:flex; align-items:center; gap:6px; font-size:12px; color:var(--text-muted); flex:0 0 auto; }
.ex-status-dot { width:7px; height:7px; border-radius:50%; flex:0 0 7px; }
.ex-dates { font-family:var(--font-mono); font-size:12px; color:var(--text-muted); margin-top:6px; }
.ex-items { display:flex; align-items:baseline; gap:4px; font-size:12px; color:var(--text-dim); margin-top:8px; flex-wrap:wrap; }
.ex-items .ids { font-family:var(--font-mono); color:var(--text-muted); }
.ex-empty { padding:32px 10px; text-align:center; color:var(--text-dim); font-size:13px; }
"""


def _fmt_date(d: datetime.date) -> str:
    return f"{d.day:02d} {_MONTHS_FR[d.month - 1]}"


def render_externat_cockpit() -> None:
    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)

    stages = externat_store.get_all_stages()

    with ui.column().classes("ex-wrap gap-0"):
        with ui.element("div").classes("ex-topbar"):
            ui.label("Externat").classes("ex-title")
            ui.label("Stages cliniques · items rattachés").classes("ex-subtitle")

        if not stages:
            with ui.element("div").classes("ex-empty"):
                ui.label("Aucun stage enregistré.")
            return

        with ui.element("div").classes("ex-list"):
            for stage in stages:
                _draw_card(stage)


def _draw_card(stage) -> None:
    courses = externat_service.get_stage_courses(stage)
    item_numbers = [c.item_number for c in courses if c.item_number]

    with ui.element("div").classes("ex-card"):
        with ui.element("div").classes("ex-card-head"):
            ui.label(stage.specialty).classes("ex-card-title")
            with ui.element("div").classes("ex-status"):
                ui.element("span").classes("ex-status-dot").style(
                    f"background:{_STATUS_COLOR.get(stage.status_label, 'var(--text-dim)')}")
                ui.label(stage.status_label)

        ui.label(f"{_fmt_date(stage.start_date)} → {_fmt_date(stage.end_date)}").classes("ex-dates")

        with ui.element("div").classes("ex-items"):
            if not item_numbers:
                ui.label("Aucun item rattaché.")
            else:
                shown = item_numbers[:6]
                extra = len(item_numbers) - len(shown)
                ids_txt = " · ".join(shown) + (f" · +{extra}" if extra > 0 else "")
                ui.label("Items rattachés : ")
                ui.label(ids_txt).classes("ids")
