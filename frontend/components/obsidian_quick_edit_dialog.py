"""
obsidian_quick_edit_dialog.py — Synapse
---------------------------------------
Modale NiceGUI d'ajout rapide d'un moyen mnémotechnique, piège EDN ou d'une image
directement dans la note Obsidian du cours.
"""

from __future__ import annotations
from typing import Callable, Optional
from nicegui import ui, events
from loguru import logger

from backend.core.obsidian.service import obsidian_service


def open_obsidian_quick_edit_dialog(
    course,
    on_success: Optional[Callable[[], None]] = None,
) -> None:
    """Ouvre une modale permettant de saisir un texte et/ou d'uploader une image vers la note Obsidian."""
    if course is None:
        ui.notify("Aucun cours sélectionné", type="warning")
        return

    with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg p-6 bg-slate-900 text-white rounded-xl shadow-2xl border border-slate-700"):
        ui.label(f"💡 Ajouter à Obsidian — Item {getattr(course, 'display_item_number', '')}").classes("text-lg font-bold text-indigo-400 mb-2")
        ui.label(course.title).classes("text-sm text-slate-400 mb-4")

        # Type d'élément
        target_section = ui.radio(
            options={"mnemo": "💡 Moyen Mnémotechnique / À savoir", "piege": "⚠️ Piège EDN / Zéro au dossier"},
            value="mnemo",
        ).props("inline color=indigo").classes("mb-4 text-sm")

        # Zone de texte
        text_input = ui.textarea(
            label="Texte ou mnémotechnique",
            placeholder="Ex: TRAP: Tension / Remplissage / Atropine / Pace...",
        ).props("outlined dark rows=3").classes("w-full mb-4 text-slate-200")

        # Zone upload image
        image_bytes: list[bytes] = []
        image_filename: list[str] = []

        def handle_upload(e: events.UploadEventArguments):
            try:
                content = e.content.read()
                image_bytes.clear()
                image_bytes.append(content)
                image_filename.clear()
                image_filename.append(e.name)
                ui.notify(f"Image chargée : {e.name}", type="positive")
            except Exception as exc:
                logger.error(f"Erreur upload image : {exc}")
                ui.notify("Erreur lors du chargement de l'image", type="negative")

        ui.label("📷 Image / Schéma (optionnel)").classes("text-xs font-semibold text-slate-400 mb-1")
        ui.upload(
            on_upload=handle_upload,
            max_files=1,
            auto_upload=True,
        ).props("accept='image/*' flat bordered dark").classes("w-full mb-4 text-xs")

        def submit():
            txt = text_input.value or ""
            img_b = image_bytes[0] if image_bytes else None
            img_fn = image_filename[0] if image_filename else None

            if not txt and not img_b:
                ui.notify("Saisissez du texte ou joignez une image", type="warning")
                return

            ok = obsidian_service.append_mnemonic_or_image(
                course,
                text_content=txt if txt else None,
                image_bytes=img_b,
                image_filename=img_fn,
                target_section=target_section.value,
            )

            if ok:
                ui.notify("Note Obsidian mise à jour !", type="positive", icon="check_circle")
                dialog.close()
                if on_success:
                    on_success()
            else:
                ui.notify("Impossible de mettre à jour la note Obsidian", type="negative")

        with ui.row().classes("w-full justify-end gap-3 mt-2"):
            ui.button("Annuler", on_click=dialog.close).props("flat color=grey")
            ui.button("Enregistrer sur Obsidian", on_click=submit).props("unelevated color=indigo icon=save")

    dialog.open()
