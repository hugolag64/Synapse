"""
triage.py — Écran de triage groupé d'un collège validé
------------------------------------------------------
Option A de la spec : attribuer en une passe un niveau déclaré aux items d'un
collège validé. Toujours facultatif — le triage progressif (au fil des sessions)
reste le chemin par défaut.

Quittable à tout moment : ce qui est trié est acquis, le reste reste « à situer ».
"""
from urllib.parse import unquote

from nicegui import ui

from frontend.theme import frame
from backend.state.store import data_store
from backend.core.knowledge import store as knowledge_store
from backend.core.reviews.service import review_service


LEVELS = [
    ("solide",  "Solide",  "positive"),
    ("correct", "Correct", "warning"),
    ("flou",    "Flou",    "negative"),
]


@ui.page("/triage/{college}")
@frame("Triage")
def triage_page(college: str):
    college = unquote(college)

    if not data_store.is_loaded:
        ui.label("Chargement des données…").classes("text-slate-500")
        return

    courses = data_store.get_cours_for_college(college)
    if not courses:
        ui.label(f"Aucun item dans {college}.").classes("text-slate-500")
        return

    root = ui.column().classes("w-full gap-0")

    def _render():
        states = knowledge_store.get_all_item_states("college")
        situes = sum(1 for c in courses if c.id in states)

        root.clear()
        with root:
            ui.label(f"Triage — {college}").classes(
                "synapse-display text-[22px] font-extrabold text-slate-900 "
                "dark:text-slate-50 tracking-tight"
            )
            ui.label(
                f"{situes} items situés sur {len(courses)} · "
                "les items non triés restent « à situer » et te seront proposés au fil des révisions."
            ).classes("text-xs text-slate-500 mb-4")

            for c in courses:
                current = states.get(c.id)

                with ui.row().classes(
                    "items-center justify-between w-full gap-3 py-2 "
                    "border-b border-slate-100 dark:border-slate-800"
                ):
                    item_txt = f"ITEM {c.item_number} — " if c.item_number else ""
                    ui.label(f"{item_txt}{c.title}").classes(
                        "text-sm text-slate-800 dark:text-slate-100 flex-1 truncate"
                    )

                    with ui.row().classes("gap-1 shrink-0"):
                        for level, label, color in LEVELS:
                            selected = current is not None and current.declared_level == level

                            def _set(_cid=c.id, _level=level):
                                knowledge_store.set_item_state(
                                    _cid, _level, context="college", source="triage"
                                )
                                review_service.invalidate_cache()
                                _render()

                            ui.button(label, on_click=_set).props(
                                f"unelevated rounded size=sm color={color}"
                                if selected else
                                "outline rounded size=sm color=grey"
                            )

            ui.button(
                "Retour aux collèges",
                on_click=lambda: ui.navigate.to("/colleges"),
            ).props("flat dense color=indigo").classes("mt-4")

    _render()
