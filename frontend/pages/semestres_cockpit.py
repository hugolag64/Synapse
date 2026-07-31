"""semestres_cockpit.py — Vue « Semestres » cockpit (refonte, session 8).

Vue principale de l'écran Semestres.
semestres.py). Une carte par semestre : titre « Semestre N — UE1 · UE2 · … »
+ pourcentage (couleur santé), barre de progression, nombre d'items. Le
chemin classic (onglets Semestre → filtre UE → grille de CourseCard) reste
strictement inchangé.

Écarts assumés (voir Journal du CLAUDE.md de la refonte) :
  • même hiérarchie que le classic (`cours.semestre` → `cours.ue_id` →
    `data_store.ues_map`), reconstruite ici plutôt qu'exposée par le
    backend — aucun helper `get_semestres_hierarchy()` n'existe ;
  • « progression » = même définition que Collèges (session 7) : part des
    cours du semestre ayant `date_1ere_lecture` renseigné ;
  • tri des semestres = `sorted(hierarchy.keys())`, identique au classic
    (chaînes du type "Semestre N" ; ne gère pas un tri numérique correct
    au-delà de Semestre 9, mais c'est déjà le comportement classic, pas
    modifié ici).
"""
from __future__ import annotations

from nicegui import ui

from backend.state.store import data_store
from frontend.components.mastery_indicator import _LEVEL_COLOR, _level_from_score

_CSS = """
.sm-wrap { max-width:900px; width:100%; }
.sm-topbar { padding:4px 0 18px; }
.sm-title { font-size:20px; font-weight:600; color:var(--text); letter-spacing:-0.01em; }
.sm-subtitle { font-size:12.5px; color:var(--text-muted); margin-top:4px; }
.sm-list { display:flex; flex-direction:column; gap:12px; width:100%; }
.sm-card { border:1px solid var(--border); border-radius:8px; padding:16px 18px; }
.sm-card-head { display:flex; align-items:baseline; justify-content:space-between; gap:12px; }
.sm-card-title { font-size:14.5px; font-weight:600; color:var(--text); line-height:1.4; }
.sm-card-pct { font-family:var(--font-mono); font-size:13px; font-weight:600; flex:0 0 auto; }
.sm-bar-track { height:6px; border-radius:3px; background:var(--surface-hover); overflow:hidden; margin-top:10px; }
.sm-bar-fill { height:100%; border-radius:3px; transition: width var(--duration-base) var(--ease-standard); }
.sm-card-items { font-size:11.5px; color:var(--text-dim); margin-top:8px; }
.sm-empty { padding:32px 10px; text-align:center; color:var(--text-dim); font-size:13px; }
"""


def _build_hierarchy() -> dict[str, dict[str, list]]:
    hierarchy: dict[str, dict[str, list]] = {}
    for cours in data_store.cours:
        if not cours.ue_id:
            continue
        semestre = cours.semestre if cours.semestre else "Non classé"
        ue_nom = "Sans UE"
        if cours.ue_id in data_store.ues_map:
            ue_data = data_store.ues_map[cours.ue_id]
            ue_nom = ue_data.get("nom") or "Sans UE"
            if semestre == "Non classé" and ue_data.get("semestre"):
                semestre = ue_data.get("semestre")
        hierarchy.setdefault(semestre, {}).setdefault(ue_nom, []).append(cours)
    return hierarchy


def render_semestres_cockpit() -> None:
    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)

    hierarchy = _build_hierarchy()

    with ui.column().classes("sm-wrap gap-0"):
        with ui.element("div").classes("sm-topbar"):
            ui.label("Semestres").classes("sm-title")
            ui.label("Progression par UE / semestre").classes("sm-subtitle")

        if not hierarchy:
            with ui.element("div").classes("sm-empty"):
                ui.label("Aucun cours rattaché à une UE.")
            return

        with ui.element("div").classes("sm-list"):
            for semestre in sorted(hierarchy.keys()):
                ue_map = hierarchy[semestre]
                ue_names = sorted(n for n in ue_map if n != "Sans UE")
                if "Sans UE" in ue_map:
                    ue_names.append("Sans UE")

                courses = [c for courses in ue_map.values() for c in courses]
                total = len(courses)
                started = sum(1 for c in courses if c.date_1ere_lecture)
                pct_int = int(round((started / total) * 100)) if total else 0
                color = _LEVEL_COLOR.get(_level_from_score(pct_int), "var(--text-muted)")

                with ui.element("div").classes("sm-card"):
                    with ui.element("div").classes("sm-card-head"):
                        ui.label(f"{semestre} — {' · '.join(ue_names)}").classes("sm-card-title")
                        ui.label(f"{pct_int}%").classes("sm-card-pct").style(f"color:{color}")
                    with ui.element("div").classes("sm-bar-track"):
                        ui.element("div").classes("sm-bar-fill").style(
                            f"width:{pct_int}%; background:{color}")
                    ui.label(f"{total} items").classes("sm-card-items")
