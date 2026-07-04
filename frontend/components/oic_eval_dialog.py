"""
oic_eval_dialog.py — Synapse
------------------------------
Dialog de validation active d'un OIC via AnythingLLM : génère 3-5 questions
(QCM + ouvertes) grounded RAG sur le workspace du collège, quiz une question
à la fois avec feedback immédiat, puis récapitulatif et progression de niveau.
"""
from __future__ import annotations

import asyncio
import json

from nicegui import ui

from backend.core.reviews import local_store as ls
from backend.core.lisa import evaluator
from backend.core.lisa.anythingllm_client import (
    resolve_workspace_slug,
    AnythingLLMUnavailableError,
    WorkspaceNotFoundError,
)

_VERDICT_COLORS = {"correct": "green-600", "partial": "orange-500", "incorrect": "red-600"}
_VERDICT_LABELS = {"correct": "ACQUIS", "partial": "PARTIEL", "incorrect": "ÉCHEC"}


def open_oic_eval_dialog(oic, course, refresh_fn=None) -> None:
    """Ouvre la dialog de quiz IA pour valider un OIC via AnythingLLM."""
    item_number = str(getattr(course, "display_item_number", "") or "")
    course_title = f"ITEM {item_number} - {course.title}" if item_number else (course.title or "")
    college_name = course.college[0] if getattr(course, "college", None) else ""

    state: dict = {
        "questions": [],
        "index": 0,
        "results": [],
        "records": [],
        "workspace_slug": None,
        "level": oic["oic_level"] or 0,
    }

    with ui.dialog() as dialog, ui.card().classes("w-[600px] max-w-[95vw] p-4 rounded-2xl"):
        with ui.row().classes("w-full items-center justify-between mb-2"):
            ui.label(f"{oic['oic_code'] or ''} · Rang {oic['rang']}").classes("font-semibold text-sm")
            ui.button(icon="close", on_click=dialog.close).props("flat dense round size=sm")

        content_area = ui.column().classes("w-full gap-3")

    def _render_error(message: str) -> None:
        content_area.clear()
        with content_area:
            ui.icon("wifi_off", color="red").classes("text-3xl self-center")
            ui.label(message).classes("text-sm text-red-500 text-center")

    def _render_loading(message: str) -> None:
        content_area.clear()
        with content_area:
            ui.spinner(size="lg").classes("self-center")
            ui.label(message).classes("text-sm text-slate-400 text-center")

    def _render_feedback(result) -> None:
        content_area.clear()
        with content_area:
            ui.label(f"{_VERDICT_LABELS[result.verdict]} · {result.score}%").classes(
                f"font-bold text-{_VERDICT_COLORS[result.verdict]}"
            )
            if result.explication:
                ui.label(result.explication).classes("text-sm")
            if result.rappel_cours:
                ui.label(result.rappel_cours).classes("text-xs text-slate-400 italic")
            is_last = state["index"] + 1 >= len(state["questions"])
            ui.button(
                "Voir le résultat" if is_last else "Question suivante →",
                on_click=_next_question,
            ).props("unelevated color=teal")

    def _next_question() -> None:
        state["index"] += 1
        if state["index"] >= len(state["questions"]):
            _render_recap()
        else:
            _render_question()

    def _render_question() -> None:
        content_area.clear()
        q = state["questions"][state["index"]]
        with content_area:
            ui.label(f"Question {state['index'] + 1}/{len(state['questions'])}").classes(
                "text-xs text-slate-400"
            )
            ui.label(q.enonce).classes("text-base font-medium")

            if q.type == "qcm":
                radio = ui.radio({i: opt for i, opt in enumerate(q.options or [])}).classes("w-full")

                def _submit_qcm(r=radio, question=q) -> None:
                    if r.value is None:
                        ui.notify("Choisissez une réponse", type="warning")
                        return
                    result = evaluator.grade_qcm(question, r.value)
                    state["results"].append(result)
                    state["records"].append({
                        "enonce": question.enonce, "type": "qcm",
                        "reponse": question.options[r.value] if question.options else "",
                        "verdict": result.verdict, "score": result.score,
                    })
                    _render_feedback(result)

                ui.button("Valider", on_click=_submit_qcm).props("unelevated color=teal")
            else:
                textarea = ui.textarea(label="Votre réponse").props("outlined").classes("w-full")

                async def _submit_open(t=textarea, question=q) -> None:
                    response = (t.value or "").strip()
                    if not response:
                        ui.notify("Répondez avant de valider", type="warning")
                        return
                    _render_loading("Correction en cours…")
                    try:
                        result = await asyncio.to_thread(
                            evaluator.evaluate_open_answer, question, response, state["workspace_slug"]
                        )
                    except AnythingLLMUnavailableError as exc:
                        _render_error(f"AnythingLLM inaccessible : {exc}")
                        return
                    state["results"].append(result)
                    state["records"].append({
                        "enonce": question.enonce, "type": "ouverte", "reponse": response,
                        "verdict": result.verdict, "score": result.score,
                    })
                    _render_feedback(result)

                ui.button("Valider", on_click=_submit_open).props("unelevated color=teal")

    def _render_recap() -> None:
        content_area.clear()
        session_score = evaluator.aggregate_session_score(state["results"])
        previous = [row["session_score"] for row in ls.get_oic_attempts(oic["id"], limit=2)]
        old_level = state["level"]
        new_level = evaluator.next_oic_level(old_level, session_score, previous)
        ls.save_oic_attempt(oic["id"], session_score, json.dumps(state["records"], ensure_ascii=False))
        ls.update_oic_level(oic["id"], new_level)
        state["level"] = new_level

        with content_area:
            ui.label(f"Score global : {session_score}%").classes("text-lg font-bold")
            ui.label(f"Niveau {old_level} → {new_level}").classes("text-sm text-slate-400")
            with ui.row().classes("gap-2 mt-2"):
                ui.button("Recommencer", on_click=lambda: asyncio.ensure_future(_start())).props(
                    "outline color=teal"
                )
                ui.button("Fermer", on_click=dialog.close).props("unelevated color=teal")

    async def _start() -> None:
        state["index"] = 0
        state["results"] = []
        state["records"] = []
        _render_loading("Résolution du workspace…")
        try:
            if state["workspace_slug"] is None:
                state["workspace_slug"] = await asyncio.to_thread(resolve_workspace_slug, college_name)
        except (WorkspaceNotFoundError, AnythingLLMUnavailableError) as exc:
            _render_error(str(exc))
            return

        _render_loading("Génération des questions…")
        try:
            state["questions"] = await asyncio.to_thread(
                evaluator.generate_questions, course_title, oic["intitule"], oic["rang"], state["workspace_slug"]
            )
        except AnythingLLMUnavailableError as exc:
            _render_error(str(exc))
            return
        _render_question()

    if refresh_fn:
        dialog.on("hide", lambda: refresh_fn())

    ui.timer(0.05, lambda: asyncio.ensure_future(_start()), once=True)
    dialog.open()
