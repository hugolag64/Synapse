"""Interface d'import des banques DP/KFP sans appel réseau."""

from __future__ import annotations

from dataclasses import replace

from nicegui import ui

from backend.core.practice.importer import (
    ImportValidationError,
    parse_practice_bank,
    parse_practice_discussion,
)
from backend.core.reviews import local_store


def open_practice_import_dialog(refresh=None, item_number: str = "") -> None:
    pending = {"batch": None}
    item_controls = {}
    with ui.dialog() as dialog, ui.card().classes("w-[680px] max-w-[95vw] p-5"):
        ui.label("Importer une banque QCM / DP / KFP").classes("text-lg font-semibold")
        ui.label(
            "Import local JSON préparé en amont. Aucun appel Gemini ne sera effectué."
        ).classes("text-xs text-slate-500 mb-3")
        status = ui.label("Choisis un fichier JSON version 1.").classes("text-sm")
        preview = ui.column().classes("w-full gap-1 mt-2")

        def _show_preview(batch) -> None:
            preview.clear()
            item_controls.clear()
            ready = sum(case.status == "ready" for case in batch.cases)
            review = len(batch.cases) - ready
            with preview:
                ui.label(f"{len(batch.cases)} cas · {ready} prêts · {review} à vérifier").classes(
                    "font-medium"
                )
                for case in batch.cases[:8]:
                    ui.label(f"{case.kind.upper()} · {case.title}").classes("text-xs font-medium")
                    controls = []
                    with ui.row().classes("items-center gap-2"):
                        ui.label("ITEM proposés :").classes("text-xs text-slate-500")
                        for number in case.item_numbers:
                            controls.append((number, ui.checkbox(number, value=True).props("dense")))
                        if not case.item_numbers:
                            controls.append(("manual", ui.input(placeholder="115, 222").props("dense outlined")))
                    item_controls[case.fingerprint] = controls

        def _on_upload(event) -> None:
            try:
                raw = event.content.read()
                try:
                    batch = parse_practice_bank(raw)
                except ImportValidationError:
                    batch = parse_practice_discussion(raw, source=event.name)
            except (ImportValidationError, UnicodeDecodeError) as exc:
                pending["batch"] = None
                status.set_text(f"Import refusé : {exc}")
                preview.clear()
                return
            pending["batch"] = batch
            status.set_text(f"Fichier chargé : {event.name}")
            _show_preview(batch)

        ui.upload(on_upload=_on_upload, auto_upload=True).props("accept=.json,.txt,.md,.html color=primary")

        def _import() -> None:
            batch = pending["batch"]
            if batch is None:
                status.set_text("Sélectionne d'abord un fichier JSON.")
                return
            confirmed_cases = []
            for case in batch.cases:
                controls = item_controls.get(case.fingerprint, [])
                selected = list(case.item_numbers) if not controls else []
                for number, control in controls:
                    if number == "manual":
                        selected.extend(
                            part.strip() for part in str(control.value or "").split(",")
                            if part.strip().isdigit()
                        )
                    elif control.value:
                        selected.append(number)
                selected = tuple(sorted(set(selected), key=lambda value: int(value)))
                confirmed_cases.append(replace(
                    case,
                    item_numbers=selected,
                    status="ready" if selected else "needs_review",
                    review_reason="" if selected else "ITEM introuvable ou non confirmé",
                ))
            batch = replace(batch, cases=tuple(confirmed_cases))
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
