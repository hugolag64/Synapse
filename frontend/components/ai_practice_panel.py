"""Panneau Cockpit des sessions IA, questions immuables et tentatives."""

from __future__ import annotations

import asyncio
import re

from nicegui import ui

from backend.core.practice.mastery import record_ai_practice_mastery
from backend.core.practice.models import PracticeKind, PracticeSessionSpec, QuestionKind
from backend.core.practice.service import PracticeService
from backend.core.reviews import local_store
from frontend.components.practice_import_panel import open_practice_import_dialog


def _item_number(course) -> str:
    return str(
        getattr(course, "display_item_number", "")
        or getattr(course, "item_number", "")
        or ""
    )


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _same_closed_answer(response: str, answer: str, choices: list[str]) -> bool:
    def _tokens(value: str) -> set[str]:
        raw_tokens = [part for part in re.split(r"[,;|/]", str(value or "")) if part.strip()]
        result = set()
        for token in raw_tokens:
            normalized = _norm(token)
            for index, choice in enumerate(choices):
                letter = chr(ord("a") + index)
                if normalized in {letter, _norm(choice)}:
                    normalized = letter
                    break
            result.add(normalized)
        return result

    response_norm = _norm(response)
    answer_norm = _norm(answer)
    if response_norm == answer_norm or _tokens(response) == _tokens(answer):
        return True
    for index, choice in enumerate(choices):
        letter = chr(ord("a") + index)
        if response_norm == letter and (answer_norm == letter or response_norm == _norm(choice)):
            return True
        if response_norm == _norm(choice) and answer_norm in {letter, _norm(choice)}:
            return True
    return False


def _open_generation_dialog(course, refresh) -> None:
    with ui.dialog() as dialog, ui.card().classes("ai-practice-generation-card p-5").style(
        "width: 680px; max-width: calc(100vw - 32px); border-radius: 10px;"
    ):
        ui.label("Nouvelle session IA").classes("text-lg font-semibold")
        ui.label("Les questions seront conservées et rejouables à l’identique.").classes(
            "text-xs text-slate-500 mb-4"
        )
        kind = ui.toggle(
            {"OIC": "OIC", "QCM": "QCM", "DP": "DP", "KFP": "KFP"},
            value="QCM",
        ).props("spread no-caps unelevated").classes("w-full")

        with ui.row().classes("w-full items-center justify-between mt-5"):
            total_label = ui.label().classes("text-sm font-medium")
            total_value_chip = ui.label().classes(
                "text-xs font-mono font-semibold px-2 py-1 rounded-md bg-slate-100 text-slate-700"
            )
        total = ui.slider(min=1, max=50, step=1, value=10).props("color=primary").classes("w-full")
        total.props("aria-label='Nombre total de questions'")

        with ui.row().classes("w-full items-center justify-between mt-4"):
            open_label = ui.label().classes("text-sm font-medium")
            open_value_chip = ui.label().classes(
                "text-xs font-mono font-semibold px-2 py-1 rounded-md bg-violet-50 text-violet-700"
            )
        opened = ui.slider(min=0, max=10, step=1, value=3).props("color=deep-purple").classes("w-full")
        opened.props("aria-label='Nombre de questions ouvertes'")

        distribution = ui.label().classes("text-xs text-slate-500 mt-2")
        status = ui.label().classes("text-xs text-red-500 mt-2")

        def _sync_sliders(_event=None) -> None:
            total_value = int(total.value or 1)
            opened.props(f"max={total_value}")
            opened.value = min(int(opened.value or 0), total_value)
            total_label.set_text(f"Nombre total · {total_value} question{'s' if total_value != 1 else ''}")
            total_value_chip.set_text(str(total_value))
            open_value = int(opened.value or 0)
            open_label.set_text(f"Questions ouvertes · {open_value}")
            open_value_chip.set_text(str(open_value))
            closed_value = total_value - open_value
            distribution.set_text(
                f"{open_value} ouverte{'s' if open_value != 1 else ''} · "
                f"{closed_value} fermée{'s' if closed_value != 1 else ''}"
            )

        total.on_value_change(_sync_sliders)
        opened.on_value_change(_sync_sliders)
        _sync_sliders()

        async def _generate() -> None:
            try:
                spec = PracticeSessionSpec(
                    practice_kind=PracticeKind(str(kind.value).upper()),
                    total_questions=int(total.value or 0),
                    open_questions=int(opened.value or 0),
                    closed_questions=int(total.value or 0) - int(opened.value or 0),
                    item_number=_item_number(course),
                    course_id=str(getattr(course, "id", "") or ""),
                    course_title=str(getattr(course, "title", "") or ""),
                )
            except (TypeError, ValueError) as exc:
                status.set_text(str(exc))
                return
            status.set_text("Génération en cours…")
            try:
                session_id = await asyncio.to_thread(
                    PracticeService().create_new_session, spec, str(getattr(course, "title", "") or "")
                )
            except Exception as exc:
                status.set_text(f"Échec de génération : {exc}")
                return
            dialog.close()
            ui.notify(f"Session IA #{session_id} enregistrée", type="positive")
            refresh()

        with ui.row().classes("justify-end gap-2 mt-5"):
            ui.button("Annuler", on_click=dialog.close).props("flat")
            ui.button("Générer et conserver", on_click=_generate).props("color=primary unelevated")
    dialog.open()


def _open_answer_dialog(session_id: int, refresh) -> None:
    questions = local_store.get_ai_practice_session(session_id)
    if not questions:
        ui.notify("Cette session ne contient aucune question", type="warning")
        return
    answers = {}
    with ui.dialog() as dialog, ui.card().classes("w-[760px] max-w-[96vw] p-5"):
        ui.label(f"Session IA #{session_id}").classes("text-lg font-semibold")
        ui.label("Les réponses seront ajoutées à l’historique sans modifier les questions.").classes(
            "text-xs text-slate-500 mb-3"
        )
        for index, question in enumerate(questions, start=1):
            with ui.card().classes("w-full p-3 border border-slate-200 dark:border-slate-700"):
                with ui.row().classes("w-full items-start justify-between"):
                    ui.label(f"{index}. {question['prompt']}").classes("font-medium whitespace-pre-wrap")
                    ui.button(
                        "Ancrer",
                        on_click=lambda qid=question["id"]: (
                            local_store.set_ai_practice_anchor(qid),
                            ui.notify("Question ajoutée aux ancrages", type="positive"),
                        ),
                    ).props("flat dense color=primary")
                if question["question_kind"] == QuestionKind.CLOSED.value:
                    answers[question["id"]] = [
                        (choice, ui.checkbox(choice).props("dense")) for choice in question["choices"]
                    ]
                else:
                    answers[question["id"]] = ui.textarea("Votre réponse").props("outlined autogrow").classes("w-full")

        async def _submit() -> None:
            for question in questions:
                control = answers[question["id"]]
                is_closed = question["question_kind"] == QuestionKind.CLOSED.value
                if is_closed:
                    selected = [choice for choice, box in control if box.value]
                    response = ", ".join(selected)
                else:
                    response = str(control.value or "").strip()
                correct = _same_closed_answer(response, question["answer"], question["choices"]) if is_closed else None
                score = 100.0 if correct else 0.0 if is_closed else None
                local_store.record_ai_practice_attempt(
                    session_id=session_id,
                    question_id=question["id"],
                    response=response,
                    is_correct=correct,
                    score_percent=score,
                )
            try:
                record_ai_practice_mastery(session_id)
            except Exception as exc:
                ui.notify(f"Réponses enregistrées, maîtrise non mise à jour : {exc}", type="warning")
            dialog.close()
            ui.notify("Réponses enregistrées dans l’historique", type="positive")
            refresh()

        with ui.row().classes("justify-end gap-2 mt-4"):
            ui.button("Fermer", on_click=dialog.close).props("flat")
            ui.button("Enregistrer mes réponses", on_click=_submit).props("color=primary unelevated")
    dialog.open()


def _render_history(item_number: str, refresh) -> None:
    history = local_store.get_ai_practice_history(item_number=item_number, limit=30)
    if not history:
        ui.label("Aucune question IA enregistrée pour cet ITEM.").classes("ci-empty")
        return
    for entry in history:
        session = entry["session"]
        questions = entry["questions"]
        attempted = sum(bool(q["attempts"]) for q in questions)
        with ui.expansion(
            f"Session #{session['id']} · {session['practice_kind'].upper()} · "
            f"{len(questions)} questions · {attempted}/{len(questions)} répondues",
            icon="history",
        ).classes("w-full border-b border-slate-200 dark:border-slate-700"):
            with ui.row().classes("items-center gap-2 mb-2"):
                ui.label(str(session["created_at"])[:16]).classes("text-xs text-slate-400")
                ui.label(session["model"] or "modèle inconnu").classes("text-xs font-mono text-slate-400")
                ui.button("Répondre", on_click=lambda sid=session["id"]: _open_answer_dialog(sid, refresh)).props(
                    "flat dense color=primary"
                )
                ui.button("Rejouer exactement", on_click=lambda sid=session["id"]: _replay(sid, refresh)).props(
                    "flat dense"
                )
            for question in questions:
                with ui.card().classes("w-full p-3 mb-2 bg-slate-50 dark:bg-slate-900/40"):
                    ui.label(question["prompt"]).classes("text-sm font-medium whitespace-pre-wrap")
                    ui.label(f"Correction : {question['answer']}").classes("text-xs text-green-700 dark:text-green-400 mt-1")
                    ui.label(f"Explication : {question['explanation']}").classes("text-xs text-slate-500 whitespace-pre-wrap")
                    for attempt in question["attempts"]:
                        ui.label(
                            f"Réponse du {str(attempt['answered_at'])[:16]} : {attempt['response'] or '—'}"
                        ).classes("text-xs text-blue-700 dark:text-blue-300 mt-2")


def _replay(session_id: int, refresh) -> None:
    try:
        new_id = local_store.replay_ai_practice_session(session_id)
        ui.notify(f"Session #{new_id} créée avec les mêmes questions", type="positive")
        refresh()
    except Exception as exc:
        ui.notify(str(exc), type="negative")


def _start_imported_case(case_id: int, course, refresh) -> None:
    cases = [case for case in local_store.get_imported_practice_cases(limit=500) if case["id"] == case_id]
    if not cases:
        ui.notify("Cas importé introuvable", type="warning")
        return
    case = cases[0]
    questions = []
    for question in case.get("questions", []):
        is_closed = bool(question.get("choices"))
        questions.append({
            "prompt": question["prompt"],
            "kind": QuestionKind.CLOSED.value if is_closed else QuestionKind.OPEN.value,
            "choices": question.get("choices", []),
            "answer": question["answer"],
            "explanation": question["explanation"],
        })
    open_count = sum(q["kind"] == QuestionKind.OPEN.value for q in questions)
    spec = PracticeSessionSpec(
        practice_kind=PracticeKind(str(case["kind"]).upper()),
        total_questions=len(questions),
        open_questions=open_count,
        closed_questions=len(questions) - open_count,
        item_number=_item_number(course),
        course_id=str(getattr(course, "id", "") or ""),
        course_title=str(getattr(course, "title", "") or case["title"]),
    )
    session_id = local_store.create_ai_practice_session(spec=spec, questions=questions, model="local-import")
    _open_answer_dialog(session_id, refresh)


def _start_random_imported_case(course, refresh) -> None:
    rows = local_store.get_random_imported_practice_cases(item_number=_item_number(course), limit=1)
    if not rows:
        ui.notify("Aucun cas local disponible pour cet ITEM", type="warning")
        return
    _start_imported_case(rows[0]["id"], course, refresh)


def render_ai_practice_panel(course) -> None:
    """Ajoute la génération, le rejeu et l'historique au Cockpit ITEM."""
    item_number = _item_number(course)
    container = ui.element("div").classes("w-full")

    def refresh() -> None:
        container.clear()
        with container:
            _render_content()

    def _render_content() -> None:
        with ui.row().classes("items-center justify-between w-full mb-3"):
            with ui.column().classes("gap-0"):
                ui.label("Questions IA").classes("ci-section-title")
                ui.label("Questions conservées, rejouables et comparables dans le temps.").classes(
                    "text-xs text-slate-400"
                )
            with ui.row().classes("gap-2"):
                ui.button("Importer QCM / DP / KFP", icon="upload_file", on_click=lambda: open_practice_import_dialog(
                    refresh, item_number
                )).props("flat color=primary")
                ui.button("Nouvelle session", icon="add", on_click=lambda: _open_generation_dialog(course, refresh)).props(
                    "color=primary unelevated"
                )
        _render_history(item_number, refresh)
        imported = local_store.get_imported_practice_cases(item_number=item_number, limit=20)
        if imported:
            with ui.row().classes("items-center gap-2 mt-4"):
                ui.label("Banque locale DP/KFP").classes("ci-section-title")
                ui.button("Tirer au hasard", on_click=lambda: _start_random_imported_case(course, refresh)).props(
                    "flat dense color=primary"
                )
            for case in imported:
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label(
                        f"{case['kind'].upper()} · {case['title']} · {len(case.get('questions', []))} questions"
                    ).classes("text-sm")
                    ui.button("S'entraîner", on_click=lambda cid=case["id"]: _start_imported_case(cid, course, refresh)).props(
                        "flat dense color=primary"
                    )
                if case["status"] == "needs_review":
                    ui.label(f"À vérifier : {case['review_reason']}").classes("text-xs text-amber-600")

    with container:
        _render_content()
