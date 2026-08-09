"""Panneau de gestion des calendriers Google supplémentaires (Planning)."""

from __future__ import annotations

from nicegui import ui

from backend.core.planning.calendar_sources import (
    add_calendar_source,
    list_calendar_sources,
    remove_calendar_source,
)
from backend.state.store import data_store

_CSS = """
.cs-row { display:flex; align-items:center; gap:10px; padding:8px 0; border-bottom:1px solid var(--border); }
.cs-row:last-child { border-bottom:none; }
.cs-label { font-size:12.5px; color:var(--text); flex:0 0 auto; }
.cs-id { font-family:var(--font-mono); font-size:11px; color:var(--text-muted); flex:1 1 auto;
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.cs-empty { padding:10px 0; color:var(--text-dim); font-size:12px; font-style:italic; }
"""


def _display_rows(sources: list[dict]) -> list[dict]:
    """Lignes prêtes à l'affichage : label, ou l'ID si le label est vide."""
    return [{"id": s["id"], "display_label": s["label"] or s["id"]} for s in sources]


def render(container: ui.element) -> None:
    with container:
        ui.add_head_html(f"<style>{_CSS}</style>", shared=True)
        ui.label("CALENDRIERS").classes("se-label")
        ui.label(
            "Calendriers Google supplémentaires affichés dans la grille Planning, "
            "en plus du calendrier principal."
        ).classes("se-appearance-sub")

        rows_container = ui.column().classes("w-full gap-0 mt-2")

        def _sources() -> list[dict]:
            return list_calendar_sources(data_store.preferences)

        def _redraw() -> None:
            rows_container.clear()
            sources = _sources()
            with rows_container:
                if not sources:
                    ui.label("Aucun calendrier supplémentaire configuré.").classes("cs-empty")
                for row in _display_rows(sources):
                    with ui.element("div").classes("cs-row"):
                        ui.label(row["display_label"]).classes("cs-label")
                        ui.label(row["id"]).classes("cs-id")
                        ui.button(
                            icon="close",
                            on_click=lambda cid=row["id"]: _remove(cid),
                        ).props("flat round dense size=sm color=grey")

        def _remove(calendar_id: str) -> None:
            updated = remove_calendar_source(_sources(), calendar_id)
            data_store.set_preference("planning_calendar_sources", updated)
            _redraw()
            ui.notify("Calendrier retiré", type="positive")

        with ui.row().classes("w-full gap-2 mt-3 items-end"):
            id_input = ui.input(label="ID du calendrier").props("outlined dense").classes("flex-1")
            label_input = ui.input(label="Label (optionnel)").props("outlined dense").classes("flex-1")

            def _add() -> None:
                try:
                    updated = add_calendar_source(_sources(), id_input.value or "", label_input.value or "")
                except ValueError as exc:
                    ui.notify(str(exc), type="negative")
                    return
                data_store.set_preference("planning_calendar_sources", updated)
                id_input.value = ""
                label_input.value = ""
                _redraw()
                ui.notify("Calendrier ajouté", type="positive")

            ui.button("Ajouter", on_click=_add).props("unelevated color=indigo no-caps dense")

        _redraw()
