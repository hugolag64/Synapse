"""Flash-Zero rendu dans le cockpit NiceGUI."""

from __future__ import annotations

from collections.abc import Callable

from nicegui import ui

from backend.core.practice.flash_zero_service import FlashZeroService


_CSS = """
.flash-zero-card { border:1px solid var(--border); border-left:3px solid var(--warning); border-radius:8px; background:var(--bg); box-shadow:var(--shadow-popover); transition:border-color var(--duration-fast) var(--ease-standard), background var(--duration-fast) var(--ease-standard); }
.flash-zero-card:hover { border-color:var(--border-strong); background:var(--surface); }
.flash-zero-layout { display:flex; align-items:center; gap:12px; min-width:0; }
.flash-zero-icon { width:28px; height:28px; flex:0 0 28px; display:flex; align-items:center; justify-content:center; border-radius:6px; background:rgba(229,162,63,.12); color:var(--warning); font-size:15px; }
.flash-zero-copy { flex:1; min-width:0; }
.flash-zero-title { color:var(--text); font-size:13px; font-weight:600; }
.flash-zero-meta { color:var(--text-muted); font-family:var(--font-mono); font-size:11px; }
.flash-zero-status { color:var(--text-dim); font-family:var(--font-mono); font-size:10px; }
/* Dans le flux, avant le bouton d'action : en absolute right:8px elle se
   retrouvait sous « Lancer » et n'était jamais cliquable. L'espace reste
   réservé même masquée, pour que le survol ne décale pas la carte. */
.flash-zero-dismiss { flex:0 0 auto; opacity:0; pointer-events:none; color:var(--text-muted); transition:opacity var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard); }
.flash-zero-card:hover .flash-zero-dismiss, .flash-zero-card:focus-within .flash-zero-dismiss { opacity:1; pointer-events:auto; }
.flash-zero-dismiss:hover { color:var(--danger); }
.flash-zero-answer { display:flex; flex-direction:column; gap:2px; margin-top:10px; }
.flash-zero-answer-label { font-size:10px; text-transform:uppercase; letter-spacing:.06em; color:var(--text-dim); font-weight:600; }
.flash-zero-answer-value { font-size:13px; color:var(--text); line-height:1.4; }
.flash-zero-wizard { border:1px solid var(--border); border-radius:12px; overflow:hidden; }
.flash-zero-wizard-header { border-bottom:1px solid var(--border); background:var(--surface); }
.flash-zero-wizard-progress { height:4px; border-radius:999px; background:var(--border); overflow:hidden; }
.flash-zero-wizard-progress > div { height:100%; background:var(--accent); transition:width .18s ease; }
.flash-zero-correction { border:1px solid var(--border); border-radius:8px; padding:14px; background:var(--bg-alt); }
.flash-zero-correction.good { border-color:var(--success); background:color-mix(in srgb, var(--success) 8%, var(--bg-alt)); }
.flash-zero-correction.bad { border-color:var(--danger); background:color-mix(in srgb, var(--danger) 7%, var(--bg-alt)); }
@media (max-width: 560px) { .flash-zero-status { display:none; } }
"""


def flash_zero_card_model(entry: dict, *, completed: bool) -> dict[str, str]:
    return {
        "title": str(entry.get("course_title") or "Flash-Zero du matin"),
        "duration": f"{int(entry.get('duration_minutes') or 5)} min",
        "status": "Fait" if completed else "À faire",
        "action": "Rejouer" if completed else "Lancer",
    }


def open_flash_zero_quiz(
    *, service: FlashZeroService | None = None, on_complete: Callable[[], None] | None = None
) -> None:
    service = service or FlashZeroService()
    questions = service.get_morning_quiz(count=10)
    state = {
        "index": 0,
        "phase": "question",
        "selected_idx": None,
        "score": 0,
        "zero_errors": 0,
        "results": [],
        "completed_notified": False,
    }

    with ui.dialog() as dialog, ui.card().classes("flash-zero-wizard w-[720px] max-w-[95vw] p-0 gap-0"):
        body = ui.column().classes("w-full gap-3")

        def draw() -> None:
            body.clear()
            with body:
                if state["index"] >= len(questions):
                    ui.label("Flash-Zero terminé").classes("text-lg font-semibold")
                    ui.label(f"Score : {state['score']} / {len(questions)}").classes("text-base")
                    ui.label(
                        f"{state['zero_errors']} erreur(s) sur les pièges zéro éliminatoire(s)."
                    ).classes("text-sm text-slate-500")
                    if state["results"]:
                        with ui.column().classes("w-full gap-1"):
                            ui.label("Résumé").classes("text-xs font-semibold uppercase tracking-wide text-slate-500")
                            for result in state["results"]:
                                ui.label(
                                    f"{result['item']} · {'Correct' if result['is_correct'] else 'À revoir'}"
                                ).classes("text-sm")
                    ui.button("Fermer", on_click=dialog.close).props("flat")
                    if on_complete and not state["completed_notified"]:
                        state["completed_notified"] = True
                        on_complete()
                    return
                question = questions[state["index"]]
                with ui.column().classes("w-full gap-0 p-5"):
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label("Flash-Zero · 5 min").classes("text-lg font-semibold")
                        ui.label(f"{state['index'] + 1} / {len(questions)}").classes("text-xs font-mono text-slate-500")
                    with ui.element("div").classes("flash-zero-wizard-progress w-full mt-3"):
                        ui.element("div").style(f"width:{((state['index'] + (state['phase'] == 'correction')) / len(questions)) * 100:.0f}%")
                    ui.label(f"{question.item_number} · {question.category}").classes("text-xs text-slate-500 mt-4")
                    ui.label(question.question_text).classes("text-base font-medium mt-1")

                    if state["phase"] == "question":
                        choices = ui.radio(list(question.choices), value=None).props("dense").classes("mt-3")

                        def validate() -> None:
                            if choices.value is None:
                                ui.notify("Choisis une réponse", type="warning")
                                return
                            selected = question.choices.index(choices.value)
                            is_correct = selected == question.correct_idx
                            state["selected_idx"] = selected
                            state["score"] += int(is_correct)
                            state["zero_errors"] += int(not is_correct and question.is_zero_eliminatoire)
                            state["results"].append({
                                "item": question.item_number,
                                "is_correct": is_correct,
                                "selected": selected,
                            })
                            state["phase"] = "correction"
                            draw()

                        ui.button("Valider", on_click=validate).props("unelevated color=indigo").classes("mt-3")
                    else:
                        selected = state["selected_idx"]
                        is_correct = selected == question.correct_idx
                        with ui.element("div").classes(
                            f"flash-zero-correction {'good' if is_correct else 'bad'} mt-4"
                        ):
                            ui.label("Correction").classes("text-xs font-semibold uppercase tracking-wide text-slate-500")
                            ui.label("Bonne réponse" if is_correct else "À revoir").classes("text-sm font-semibold")
                            if selected is not None:
                                with ui.element("div").classes("flash-zero-answer"):
                                    ui.label("Ta réponse").classes("flash-zero-answer-label")
                                    ui.label(question.choices[selected]).classes("flash-zero-answer-value")
                            with ui.element("div").classes("flash-zero-answer"):
                                ui.label("Réponse attendue").classes("flash-zero-answer-label")
                                ui.label(question.choices[question.correct_idx]).classes("flash-zero-answer-value")
                            ui.label(question.explanation).classes("text-sm text-slate-600 mt-3")
                        def next_question() -> None:
                            state["index"] += 1
                            state["phase"] = "question"
                            state["selected_idx"] = None
                            draw()

                        ui.button("Question suivante", on_click=next_question).props("unelevated color=indigo").classes("mt-3")

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
    with ui.element("div").classes("flash-zero-card w-full p-3 mb-4"):
        with ui.element("div").classes("flash-zero-layout w-full"):
            ui.label("⚡").classes("flash-zero-icon")
            with ui.element("div").classes("flash-zero-copy"):
                ui.label(model["title"]).classes("flash-zero-title")
                ui.label("Erreurs récentes et répétées").classes("flash-zero-meta")
            ui.label(f"{model['duration']} · {model['status']}").classes("flash-zero-status")
            ui.button(icon="close", on_click=on_dismiss).props(
                'flat round dense aria-label="Ignorer le Flash-Zero du jour"'
            ).classes("flash-zero-dismiss")
            ui.button(model["action"], on_click=on_open).props(
                "unelevated color=primary size=sm rounded"
            )
