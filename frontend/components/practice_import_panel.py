"""Interface d'import des banques DP/KFP sans appel réseau."""

from __future__ import annotations

from nicegui import ui

from backend.core.practice.importer import ImportValidationError, parse_practice_bank
from backend.core.reviews import local_store


def open_practice_import_dialog(refresh=None, item_number: str = "") -> None:
    pending = {"batch": None}
    with ui.dialog() as dialog, ui.card().classes("w-[680px] max-w-[95vw] p-5"):
        ui.label("Importer une banque DP/KFP").classes("text-lg font-semibold")
        ui.label(
            "Import local JSON préparé en amont. Aucun appel Gemini ne sera effectué."
        ).classes("text-xs text-slate-500 mb-3")
        status = ui.label("Choisis un fichier JSON version 1.").classes("text-sm")
        preview = ui.column().classes("w-full gap-1 mt-2")

        def _show_preview(batch) -> None:
            preview.clear()
            ready = sum(case.status == "ready" for case in batch.cases)
            review = len(batch.cases) - ready
            with preview:
                ui.label(f"{len(batch.cases)} cas · {ready} prêts · {review} à vérifier").classes(
                    "font-medium"
                )
                for case in batch.cases[:8]:
                    label = f"{case.kind.upper()} · {case.title} · ITEM {', '.join(case.item_numbers) or 'à identifier'}"
                    ui.label(label).classes("text-xs text-slate-500")

        def _on_upload(event) -> None:
            try:
                batch = parse_practice_bank(event.content.read())
            except (ImportValidationError, UnicodeDecodeError) as exc:
                pending["batch"] = None
                status.set_text(f"Import refusé : {exc}")
                preview.clear()
                return
            pending["batch"] = batch
            status.set_text(f"Fichier chargé : {event.name}")
            _show_preview(batch)

        ui.upload(on_upload=_on_upload, auto_upload=True).props("accept=.json color=primary")

        def _import() -> None:
            batch = pending["batch"]
            if batch is None:
                status.set_text("Sélectionne d'abord un fichier JSON.")
                return
            result = local_store.import_practice_batch(batch)
            dialog.close()
            ui.notify(
                f"{result['inserted']} cas importé(s) · {result['duplicates']} doublon(s) · "
                f"{result['needs_review']} à vérifier",
                type="positive",
            )
            if refresh:
                refresh()

        with ui.row().classes("justify-end gap-2 mt-5"):
            ui.button("Annuler", on_click=dialog.close).props("flat")
            ui.button("Importer dans Synapse", on_click=_import).props("color=primary unelevated")
    dialog.open()
