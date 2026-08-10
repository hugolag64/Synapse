"""Contrôle UI du pont local de capture EDNpro."""

from __future__ import annotations

from nicegui import ui

LOCAL_AGENT_URL = "http://127.0.0.1:8876"


def open_ednpro_capture_dialog(refresh_fn=None) -> None:
    with ui.dialog() as dialog, ui.card().classes("w-[520px] max-w-[92vw]"):
        ui.label("Capturer une session EDNpro").classes("text-lg font-semibold")
        ui.label(
            "Réponds normalement dans Chromium. Seules les questions dont la correction "
            "est déjà affichée seront importées."
        ).classes("text-sm text-gray-600")
        status = ui.label("Agent local non démarré").classes("text-sm")
        with ui.row().classes("w-full justify-end gap-2 mt-4"):
            ui.button("Fermer", on_click=dialog.close).props("flat")

            def stop_capture() -> None:
                ui.run_javascript(
                    f"fetch('{LOCAL_AGENT_URL}/stop').then(() => window.setTimeout(() => location.reload(), 1800))"
                )
                status.set_text("Arrêt demandé : import des corrections en cours…")
                ui.notify("Import demandé. La question non corrigée est ignorée.", type="positive")

            ui.button("Arrêter et importer", icon="stop", on_click=stop_capture).props("color=primary")

            def start_capture() -> None:
                ui.run_javascript(
                    f"fetch('{LOCAL_AGENT_URL}/start').then(() => window.setTimeout(() => location.reload(), 400))"
                )
                status.set_text("Capture active dans Chromium")
                ui.notify("Capture active. Fais ta session manuellement dans Chromium.", type="positive")

            ui.button("Démarrer la capture", icon="play_arrow", on_click=start_capture)
    dialog.open()
