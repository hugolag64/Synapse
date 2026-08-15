"""Local catalog administration embedded in Paramètres."""

from __future__ import annotations

import os
from pathlib import Path

from nicegui import ui

from backend.state.catalog_import import CatalogImportService
from backend.state.catalog_repository import CatalogRepository


def render_catalog_admin() -> None:
    repository = CatalogRepository(os.getenv("SYNAPSE_CATALOG_DB_PATH"))
    service = CatalogImportService(db_path=repository.db_path)
    source = Path("data_cache.json")
    preview_holder: dict[str, object] = {}

    with ui.expansion("CATALOGUE LOCAL", icon="storage").classes("w-full se-domain-expansion"):
        ui.label(
            "La base locale est la source de vérité. Notion reste consultable uniquement pour l'import initial."
        ).classes("se-appearance-sub")
        with ui.row().classes("w-full items-center gap-4 mt-3"):
            ui.label(f"{repository.count_items()} items · {repository.count_fiches()} fiches · {repository.count_archived_courses()} archivés")
            status = ui.label("Aucune opération en cours.").classes("se-uness-status")

        with ui.tabs().classes("w-full") as tabs:
            ui.tab("import", label="Import / récupération")
            ui.tab("overrides", label="Overrides")
            ui.tab("audit", label="Journal")
        with ui.tab_panels(tabs, value="import").classes("w-full"):
            with ui.tab_panel("import"):
                with ui.row().classes("items-center gap-2"):
                    def preview_import() -> None:
                        try:
                            preview = service.preview(source)
                            preview_holder["id"] = preview.id
                            status.set_text(
                                f"Prévisualisation : {preview.item_count} items, "
                                f"{preview.fiche_count} fiches, {preview.archived_course_count} archivés."
                            )
                        except Exception as exc:
                            status.set_text(f"Erreur de prévisualisation : {exc}")

                    def apply_import() -> None:
                        preview_id = preview_holder.get("id")
                        if not preview_id:
                            status.set_text("Lance d'abord la prévisualisation.")
                            return
                        try:
                            run = service.apply(source, str(preview_id))
                            status.set_text(f"Import appliqué. Sauvegarde : {run.backup_path}")
                        except Exception as exc:
                            status.set_text(f"Import annulé : {exc}")

                    ui.button("Prévisualiser", icon="preview", on_click=preview_import).props("outline")
                    ui.button("Appliquer", icon="save", on_click=apply_import).props("unelevated color=primary")
                ui.label("Chaque import est sauvegardé et peut être restauré depuis la base locale.").classes("se-appearance-sub mt-2")

            with ui.tab_panel("overrides"):
                item_id = ui.input("ID item local").props("outlined dense")
                college_id = ui.input("ID collège local").props("outlined dense")
                action = ui.select(["add", "remove"], value="add", label="Action").props("outlined dense")
                justification = ui.input("Justification obligatoire").props("outlined dense")

                def save_override() -> None:
                    try:
                        repository.save_override(item_id.value, college_id.value, action.value, justification.value)
                        ui.notify("Override enregistré dans le journal local.", type="positive")
                    except Exception as exc:
                        ui.notify(str(exc), type="negative")

                ui.button("Enregistrer l'override", icon="edit", on_click=save_override).props("unelevated color=primary")

            with ui.tab_panel("audit"):
                entries = repository.list_audit_log(limit=30)
                if not entries:
                    ui.label("Aucune modification locale enregistrée.").classes("se-appearance-sub")
                for entry in entries:
                    ui.label(
                        f"{entry['created_at']} · {entry['operation']} · {entry['entity_id']}"
                    ).classes("text-xs font-mono")
