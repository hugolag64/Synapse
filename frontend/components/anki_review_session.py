from __future__ import annotations

import re

from nicegui import ui

from backend.core.anki.client import AnkiClient, AnkiConnectError
from backend.core.anki.media import embed_anki_media
from backend.core.anki.review import AnkiReviewController
from backend.core.reviews import local_store


def open_anki_review_session(item_number: str | None = None) -> None:
    client = AnkiClient()
    controller = AnkiReviewController(client, local_store)
    dialog = ui.dialog()
    ui.add_css(
        ".anki-card-content { width:100%; overflow:auto; }"
        ".anki-card-content #io-wrapper { display:block !important; width:fit-content; max-width:100%; margin:0 auto !important; padding:16px !important; background:#fff !important; }"
        ".anki-card-content .io-img-container { position:relative !important; display:inline-block !important; max-width:100%; }"
        ".anki-card-content #io-image { position:relative !important; z-index:1; }"
        ".anki-card-content #io-image img { display:block; max-width:100%; height:auto; }"
        ".anki-card-content #io-overlay { position:absolute !important; inset:0 !important; z-index:2; pointer-events:none; }"
        ".anki-card-content #io-overlay img { display:block; max-width:100%; height:auto; }"
    )

    with dialog, ui.card().classes("w-[min(760px,calc(100vw-32px))] max-h-[90vh] p-0"):
        header = ui.row().classes("w-full items-center justify-between px-6 py-4 border-b")
        with header:
            ui.label("Réviser avec Anki").classes("text-lg font-semibold")
            ui.button(icon="close", on_click=dialog.close).props("flat round")
        body = ui.column().classes("w-full gap-4 px-6 py-5 overflow-y-auto")
        footer = ui.row().classes("w-full justify-end gap-2 px-6 py-4 border-t")

    state = {"card": None, "answer_visible": False}
    media_cache: dict[str, bytes | None] = {}

    def render_anki_html(value: str) -> str:
        def retrieve(filename: str) -> bytes | None:
            if filename not in media_cache:
                try:
                    media_cache[filename] = client.retrieve_media_file(filename)
                except AnkiConnectError:
                    media_cache[filename] = None
            return media_cache[filename]

        value = re.sub(r"<style\b[^>]*>.*?</style\s*>", "", value or "", flags=re.IGNORECASE | re.DOTALL)
        value = re.sub(r"<script\b[^>]*>.*?</script\s*>", "", value, flags=re.IGNORECASE | re.DOTALL)
        return embed_anki_media(value, retrieve)

    def render_card() -> None:
        body.clear()
        with body:
            card = state["card"]
            if card is None:
                ui.label("Aucune carte à réviser pour cet item.").classes("text-slate-500")
                return
            ui.label(f"Item {item_number or '—'} · {card.deck_name.rsplit('::', 1)[-1]}").classes(
                "text-xs uppercase tracking-wide text-slate-500"
            )
            question = card.question_html or card.fields.get("Question Mask") or card.fields.get("Front") or ""
            answer = card.answer_html or card.fields.get("Answer Mask") or card.fields.get("Back") or ""
            ui.label("Question").classes("text-sm font-medium text-slate-500")
            ui.html(render_anki_html(question), sanitize=False).classes("anki-card-content")
            if state["answer_visible"]:
                ui.label("Réponse").classes("text-sm font-medium text-slate-500")
                ui.html(render_anki_html(answer), sanitize=False).classes("anki-card-content")
                with ui.row().classes("w-full justify-center gap-2 pt-3"):
                    for ease, label in ((1, "À revoir"), (2, "Difficile"), (3, "Correct"), (4, "Facile")):
                        ui.button(label, on_click=lambda e=ease: answer(e)).props("outline")
            else:
                ui.button("Afficher la réponse", on_click=show_answer).props("unelevated color=primary")

    def show_answer() -> None:
        state["answer_visible"] = True
        render_card()

    def answer(ease: int) -> None:
        try:
            state["card"] = controller.answer_current(ease)
            state["answer_visible"] = False
            render_card()
            ui.notify("Réponse enregistrée avec le scheduler Anki", type="positive")
        except (AnkiConnectError, RuntimeError, ValueError) as exc:
            ui.notify(f"Impossible d'enregistrer la réponse : {exc}", type="negative")

    try:
        state["card"] = controller.load_next(item_number)
        render_card()
        dialog.open()
    except (AnkiConnectError, OSError) as exc:
        ui.notify(f"AnkiConnect indisponible : {exc}", type="warning")
