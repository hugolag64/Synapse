"""Flash-Zero rendu dans le cockpit NiceGUI."""

from __future__ import annotations

from collections.abc import Callable

from nicegui import ui

from backend.core.practice.flash_zero_service import FlashZeroService


_CSS = """
.flash-zero-card { position:relative; border:1px solid var(--border); border-left:3px solid var(--warning); border-radius:8px; background:var(--surface); box-shadow:var(--shadow-popover); }
.flash-zero-card:hover { border-color:var(--border-strong); }
.flash-zero-dismiss { position:absolute; top:7px; right:7px; z-index:2; opacity:0; color:var(--text-muted); transition:opacity var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard); }
.flash-zero-card:hover .flash-zero-dismiss, .flash-zero-card:focus-within .flash-zero-dismiss { opacity:1; }
.flash-zero-dismiss:hover { color:var(--danger); }
"""


def flash_zero_card_model(entry: dict, *, completed: bool) -> dict[str, str]:
    return {
        "title": str(entry.get("course_title") or "Flash-Zero du matin"),
        "duration": f"{int(entry.get('duration_minutes') or 5)} min",
        "status": "Fait" if completed else "À faire",
        "action": "Rejouer" if completed else "Lancer",
    }


def open_flash_zero_quiz(*, service: FlashZeroService | None = None, on_complete: Callable[[], None] | None = None) -> None:
    service = service or FlashZeroService()
    questions = service.get_morning_quiz(count=10)
    state = {"index": 0, "score": 0}

    with ui.dialog() as dialog, ui.card().classes("w-[620px] max-w-[95vw] p-5 gap-4"):
        body = ui.column().classes("w-full gap-3")

        def draw() -> None:
            body.clear()
            with body:
                if state["index"] >= len(questions):
                    ui.label(f"Flash-Zero terminé : {state['score']} / {len(questions)}").classes("text-lg font-semibold")
                    ui.button("Fermer", on_click=dialog.close).props("flat")
                    if on_complete:
                        on_complete()
                    return
                question = questions[state["index"]]
                ui.label(f"Flash-Zero · Question {state['index'] + 1}/{len(questions)}").classes("text-sm text-slate-500")
                ui.label(f"{question.item_number} · {question.category}").classes("text-xs text-slate-500")
                ui.label(question.question_text).classes("text-base font-medium")
                choices = ui.radio(list(question.choices), value=None).props("dense")

                def validate() -> None:
                    if choices.value is None:
                        ui.notify("Choisis une réponse", type="warning")
                        return
                    selected = question.choices.index(choices.value)
                    if selected == question.correct_idx:
                        state["score"] += 1
                    state["index"] += 1
                    draw()

                ui.button("Valider", on_click=validate).props("unelevated color=indigo")

        draw()
    dialog.open()


def render_flash_zero_card(
    entry: dict,
    *,
    completed: bool,
    on_open: Callable[[], None],
    on_dismiss: Callable[[], None],
) -> None:
    model = flash_zero_card_model(entry, completed=completed)
    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)
    with ui.element("div").classes("flash-zero-card w-full p-4 mb-4"):
        ui.button(icon="close", on_click=on_dismiss).props(
            'flat round dense aria-label="Ignorer le Flash-Zero du jour"'
        ).classes("flash-zero-dismiss")
        with ui.row().classes("w-full items-center justify-between gap-3"):
            with ui.column().classes("gap-0"):
                ui.label("⚡ " + model["title"]).classes("text-sm font-semibold")
                ui.label(f"{model['duration']} · {model['status']} · erreurs récentes et répétées").classes("text-xs text-slate-500")
            ui.button(model["action"], on_click=on_open).props("unelevated color=primary size=sm rounded")
