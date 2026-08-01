"""externat_cockpit.py — Vue « Externat » cockpit (refonte, session 14).

Vue principale de l'écran Externat.
externat.py). Cartes de stage clinique : nom, statut, dates, items
rattachés. Écran purement visuel — le README §12 ne décrit qu'une liste de
cartes, sans action d'édition dans cette vue.

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
        with ui.element("div").classes("ex-topbar flex items-center justify-between"):
            with ui.column().classes("gap-0"):
                ui.label("Externat").classes("ex-title")
                ui.label("Stages cliniques · items rattachés").classes("ex-subtitle")
            from frontend.pages.externat import _open_stage_dialog
            ui.button("+ Nouveau stage", on_click=lambda: _open_stage_dialog(ui.navigate.reload)).props(
                "unelevated size=sm"
            ).style(
                "background:var(--accent); color:var(--accent-text); border-radius:6px; font-weight:500; font-size:12px;"
            )

        if not stages:
            with ui.element("div").classes("ex-empty"):
                ui.label("Aucun stage enregistré.").classes("mb-2")
                ui.button("Configurer un stage", on_click=lambda: _open_stage_dialog(ui.navigate.reload)).props(
                    "outline size=sm"
                ).style("color:var(--accent); border-color:var(--accent); border-radius:6px; font-size:12px;")
            return

        with ui.element("div").classes("ex-list"):
            for stage in stages:
                _draw_card(stage)


def _draw_card(stage) -> None:
    courses = externat_service.get_stage_courses(stage)
    items_with_ids = [c for c in courses if getattr(c, "item_number", None)]

    with ui.element("div").classes("ex-card"):
        with ui.element("div").classes("ex-card-head"):
            with ui.row().classes("items-center gap-2"):
                ui.label(stage.specialty).classes("ex-card-title")
                if stage.college_notion:
                    ui.label(f"· {stage.college_notion}").classes("text-xs text-[var(--text-muted)] font-medium")
            with ui.element("div").classes("ex-status"):
                ui.element("span").classes("ex-status-dot").style(
                    f"background:{_STATUS_COLOR.get(stage.status_label, 'var(--text-dim)')}")
                ui.label(stage.status_label)

        ui.label(f"{_fmt_date(stage.start_date)} → {_fmt_date(stage.end_date)}").classes("ex-dates")

        with ui.element("div").classes("ex-items"):
            if not items_with_ids:
                ui.label("Aucun item rattaché.")
            else:
                shown = items_with_ids[:6]
                extra = len(items_with_ids) - len(shown)
                ui.label("Items rattachés : ")
                with ui.row().classes("items-center gap-1.5 inline-flex flex-wrap"):
                    for c in shown:
                        item_num = c.item_number
                        item_id = c.id
                        ui.label(str(item_num)).classes(
                            "ids cursor-pointer hover:underline hover:text-[var(--accent)]"
                        ).on("click", lambda _, cid=item_id: ui.navigate.to(f"/cours/{cid}"))
                    if extra > 0:
                        college_param = stage.college_notion or ""
                        ui.label(f"+{extra}").classes(
                            "ids cursor-pointer font-bold text-[var(--accent)] hover:underline"
                        ).on("click", lambda _, col=college_param: ui.navigate.to(f"/items?college={col}"))

