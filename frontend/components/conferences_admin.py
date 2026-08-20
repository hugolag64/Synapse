"""Panel d'import et de validation du planning des conférences DFASM."""

from __future__ import annotations

import asyncio
from pathlib import Path

from nicegui import ui

from backend.core.conferences import service
from backend.core.qcm.items_mapping import all_college_names
from backend.core.reviews import local_store


def render_conferences_admin(container=None) -> None:
    parent = container or ui.column().classes("w-full")
    with parent:
        ui.label("PLANNING CONFÉRENCES — IMPORT").classes("se-label")
        ui.label(
            "Importe le calendrier XLS des conférences DFASM (mardi). Chaque conférence "
            "reconnue crée un événement Google Calendar et le créneau dossier UNESS "
            "17h30–19h."
        ).classes("se-appearance-sub")

        path_input = ui.input(
            label="Chemin du fichier XLS",
            placeholder=r"C:\Users\...\Calendrier Confs.xlsx",
        ).props("outlined dense").classes("w-full mt-3")
        status = ui.label("Aucun import lancé.").classes("se-uness-status")
        body = ui.column().classes("w-full gap-3 mt-3")

        def _render_body() -> None:
            body.clear()
            pending = local_store.list_conferences(match_status="needs_validation")
            pending_links = service.list_pending_uness_links()
            with body:
                if not pending:
                    ui.label("Aucune conférence à valider.").classes("text-sm text-slate-500")
                for conf in pending:
                    _render_pending(conf)
                if pending_links:
                    ui.label("Dossier UNESS à confirmer").classes("se-label mt-4")
                    for entry in pending_links:
                        _render_pending_uness_link(entry)

        def _render_pending(conf: dict) -> None:
            with ui.row().classes("w-full items-center gap-2"):
                ui.label(f"{conf['date']} — {conf['theme_raw']}").classes("text-sm flex-1")
                college_select = ui.select(
                    all_college_names(), label="Collège"
                ).props("outlined dense").classes("w-64")

                async def _validate(conf_id=conf["id"], select=college_select) -> None:
                    if not select.value:
                        ui.notify("Choisis un collège avant de valider.", type="warning")
                        return
                    await service.validate_conference(conf_id, college_name=select.value)
                    ui.notify("Conférence validée.", type="positive")
                    _render_body()

                async def _skip(conf_id=conf["id"]) -> None:
                    await service.validate_conference(conf_id, college_name=None, skip=True)
                    ui.notify("Conférence ignorée.", type="positive")
                    _render_body()

                ui.button("Valider", on_click=_validate).props("unelevated color=teal size=sm")
                ui.button("Non applicable", on_click=_skip).props("flat size=sm")

        def _render_pending_uness_link(entry: dict) -> None:
            conf = entry["conference"]
            candidates = entry["candidates"]
            options = {c["id"]: f"{c['titre']} — {c['matiere']}" for c in candidates}
            with ui.row().classes("w-full items-center gap-2"):
                ui.label(f"{conf['date']} — {conf['theme_raw']}").classes("text-sm flex-1")
                dossier_select = ui.select(
                    options, label="Dossier UNESS"
                ).props("outlined dense").classes("w-64")

                async def _link(conf_id=conf["id"], select=dossier_select) -> None:
                    if not select.value:
                        ui.notify("Choisis un dossier avant de lier.", type="warning")
                        return
                    try:
                        service.link_conference_to_uness_session(conf_id, select.value)
                    except ValueError as exc:
                        ui.notify(str(exc), type="negative")
                        _render_body()
                        return
                    ui.notify("Dossier UNESS lié à la conférence.", type="positive")
                    _render_body()

                ui.button("Lier", on_click=_link).props("unelevated color=teal size=sm")

        async def _run_import() -> None:
            path_text = path_input.value.strip()
            if not path_text:
                ui.notify("Indique le chemin du fichier XLS.", type="warning")
                return
            path = Path(path_text)
            if not path.exists():
                status.set_text(f"Fichier introuvable : {path}")
                status.style("color:var(--danger-text)")
                ui.notify("Fichier introuvable", type="negative")
                return
            try:
                summary = await service.import_conferences_from_xlsx(path)
            except ValueError as exc:
                status.set_text(f"Erreur d'import : {exc}")
                status.style("color:var(--danger-text)")
                ui.notify(str(exc), type="negative")
                return
            status.set_text(
                f"Import terminé : {summary.imported} nouvelle(s), "
                f"{summary.updated} mise(s) à jour, {summary.unchanged} inchangée(s), "
                f"{summary.needs_validation} à valider."
            )
            status.style("color:var(--success-text)")
            ui.notify("Import du planning terminé", type="positive", icon="event")
            _render_body()

        ui.button(
            "Importer le planning",
            icon="upload_file",
            on_click=lambda: asyncio.ensure_future(_run_import()),
        ).props("unelevated color=teal size=sm rounded").classes("mt-2")

        _render_body()
