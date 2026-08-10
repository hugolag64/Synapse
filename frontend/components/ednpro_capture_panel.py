"""Contrôle UI du pont local de capture EDNpro."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from nicegui import ui

LOCAL_AGENT_URL = "http://127.0.0.1:8876"
EDNPRO_START_URL = "https://ednpro.app/training-v2"


async def _agent_request(path: str) -> dict[str, Any]:
    script = f"""
        fetch('{LOCAL_AGENT_URL}{path}')
            .then(async response => {{
                const payload = await response.json();
                return {{http_status: response.status, payload}};
            }})
            .catch(error => ({{error: error.message}}))
    """
    try:
        result = await ui.run_javascript(script, timeout=5.0)
    except Exception as exc:
        return {"error": str(exc)}
    return result if isinstance(result, dict) else {"error": "Réponse invalide du relais local"}


def _status_text(status_payload: dict[str, Any]) -> str:
    if status_payload.get("error"):
        return "Relais local indisponible — lance l'installation Windows une fois."
    payload = status_payload.get("payload") or {}
    state = payload.get("state")
    labels = {
        "ready": "Relais prêt",
        "starting": "Ouverture de Chromium…",
        "capturing": "Capture active dans Chromium",
        "stopping": "Import des corrections en cours…",
        "imported": "Import terminé",
        "error": f"Erreur du relais : {payload.get('last_result', {}).get('error', 'erreur inconnue')}",
    }
    return labels.get(state, "État du relais inconnu")


def open_ednpro_capture_dialog(refresh_fn: Callable[[], None] | None = None) -> None:
    with ui.dialog() as dialog, ui.card().classes("w-[520px] max-w-[92vw]"):
        ui.label("Capturer une session EDNpro").classes("text-lg font-semibold")
        ui.label(
            "Chromium va s'ouvrir automatiquement. Réponds normalement et affiche "
            "la correction après chaque question ; seules les corrections affichées "
            "seront importées."
        ).classes("text-sm text-gray-600")
        status = ui.label("Ouverture du relais local…").classes("text-sm")
        stop_button = None

        async def refresh_status() -> dict[str, Any]:
            result = await _agent_request("/status")
            status.set_text(_status_text(result))
            return result

        async def start_capture() -> None:
            status.set_text("Ouverture de Chromium…")
            result = await _agent_request("/start")
            if result.get("error"):
                status.set_text(_status_text(result))
                ui.notify(status.text, type="negative")
                return
            payload = result.get("payload") or {}
            if payload.get("state") == "error":
                status.set_text(_status_text(result))
                ui.notify(status.text, type="negative")
                return
            status.set_text("Ouverture de Chromium…")
            ui.notify("Chromium EDNpro va s'ouvrir. Fais ta session manuellement.", type="positive")

        async def stop_capture() -> None:
            if stop_button is not None:
                stop_button.disable()
            status.set_text("Arrêt demandé : import des corrections en cours…")
            result = await _agent_request("/stop")
            if result.get("error"):
                status.set_text(_status_text(result))
                ui.notify(status.text, type="negative")
                return

            for _ in range(30):
                await asyncio.sleep(0.5)
                current = await refresh_status()
                payload = current.get("payload") or {}
                if payload.get("state") in {"imported", "error"}:
                    last_result = payload.get("last_result") or {}
                    if payload.get("state") == "imported":
                        ui.notify(
                            f"Import terminé : {last_result.get('imported_questions', 0)} "
                            f"question(s), {last_result.get('new_attempts', 0)} nouvelle(s) tentative(s).",
                            type="positive",
                        )
                        if refresh_fn:
                            refresh_fn()
                    else:
                        ui.notify(_status_text(current), type="negative")
                    return

            ui.notify("Le relais n'a pas confirmé la fin de l'import.", type="warning")

        with ui.row().classes("w-full justify-end gap-2 mt-4"):
            ui.button("Fermer", on_click=dialog.close).props("flat")
            stop_button = ui.button(
                "Arrêter et importer",
                icon="stop",
                on_click=stop_capture,
            ).props("color=primary")

    dialog.open()
    ui.timer(0.1, start_capture, once=True)
    ui.timer(1.0, refresh_status)
