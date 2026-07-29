"""Pure view models for replaying and correcting stored QCM sessions."""

from __future__ import annotations

import re
from collections.abc import Callable

from nicegui import ui

from backend.core.practice.mastery import record_ai_practice_mastery
from backend.core.reviews import local_store


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


def _is_open(question: dict) -> bool:
    return str(question.get("question_kind", question.get("kind", ""))).lower() == "open"


def build_question_result(question: dict, latest_attempt: dict | None) -> dict:
    choices = list(question.get("choices") or [])
    is_open = _is_open(question)
    response = "" if latest_attempt is None else str(latest_attempt.get("response") or "")
    explicit_status = None if latest_attempt is None else latest_attempt.get("is_correct")
    if latest_attempt is None:
        status = "unanswered"
    elif explicit_status is not None:
        status = "correct" if bool(explicit_status) else "incorrect"
    elif is_open:
        status = None
    else:
        status = "correct" if _same_closed_answer(response, question.get("answer", ""), choices) else "incorrect"
    explanation = str(question.get("explanation") or "").strip() or "Explication non disponible"
    return {
        "status": status,
        "response": response,
        "correct_answer": question.get("answer", ""),
        "explanation": explanation,
        "choices": choices,
        "is_open": is_open,
    }


def _latest_attempt(question: dict) -> dict | None:
    attempts = question.get("attempts") or []
    if not attempts:
        return None
    with_ids = [attempt for attempt in attempts if attempt.get("id") is not None]
    return max(with_ids, key=lambda attempt: attempt["id"]) if with_ids else attempts[0]


def latest_response_by_question(questions: list[dict]) -> dict[int, str]:
    """Return the most recently saved response for every stored question."""
    return {
        int(question["id"]): str((_latest_attempt(question) or {}).get("response") or "")
        for question in questions
    }


def save_response_once(
    persisted_responses: dict[int, str], question_id: int, response: str, save: Callable[[], None]
) -> bool:
    """Persist a response only when it differs from the last saved value."""
    if question_id in persisted_responses and persisted_responses[question_id] == response:
        return False
    save()
    persisted_responses[question_id] = response
    return True


def build_session_result(questions: list[dict]) -> dict:
    results = [build_question_result(question, _latest_attempt(question)) for question in questions]
    scored = [result for result in results if result["status"] in {"correct", "incorrect"}]
    correct_count = sum(result["status"] == "correct" for result in scored)
    answered_count = sum(result["status"] != "unanswered" for result in results)
    score_percent = round(correct_count / len(scored) * 100, 2) if scored else None
    return {
        "total_count": len(results),
        "answered_count": answered_count,
        "scored_count": len(scored),
        "correct_count": correct_count,
        "incorrect_count": len(scored) - correct_count,
        "unanswered_count": sum(result["status"] == "unanswered" for result in results),
        "score_percent": score_percent,
    }


def filter_question_results(results: list[dict], errors_only: bool) -> list[dict]:
    if not errors_only:
        return list(results)
    return [result for result in results if result.get("status") != "correct"]


def format_correction_summary(summary: dict) -> tuple[str, str]:
    """Format the score and question counts shown at the top of correction."""
    score = summary.get("score_percent")
    scored_count = int(summary.get("correct_count", 0)) + int(summary.get("incorrect_count", 0))
    unanswered_count = int(summary.get("unanswered_count", 0))
    total_questions = int(summary.get("total_questions", scored_count + unanswered_count))
    answered_count = int(summary.get("answered_count", total_questions - unanswered_count))
    unscored_count = max(0, answered_count - scored_count)
    score_text = "Score non disponible" if score is None else f"Score : {score:g} %"
    counts_text = (
        f"{summary.get('correct_count', 0)}/{total_questions} bonnes réponses · "
        f"{unanswered_count} sans réponse"
    )
    if unscored_count:
        suffix = "réponse non évaluée" if unscored_count == 1 else "réponses non évaluées"
        counts_text = f"{counts_text} · {unscored_count} {suffix}"
    return score_text, counts_text


def build_correction_rows(questions: list[dict], summary: dict) -> list[dict]:
    """Combine immutable questions with the summary's latest attempts."""
    latest_attempts = {
        int(attempt["question_id"]): attempt
        for attempt in summary.get("latest_attempts", [])
        if attempt.get("question_id") is not None
    }
    rows = []
    for position, question in enumerate(questions, start=1):
        result = build_question_result(question, latest_attempts.get(int(question["id"])))
        rows.append({"question": question, "position": position, **result})
    return rows


def replay_qcm_session(session_id: int) -> int | None:
    """Create an immutable replay and surface storage failures consistently."""
    try:
        return local_store.replay_ai_practice_session(session_id)
    except Exception as exc:
        ui.notify(str(exc), type="negative")
        return None


def open_qcm_correction(
    session_id: int,
    on_back: Callable[[], None],
    on_replay: Callable[[int], None],
) -> None:
    """Open the compact, immutable correction view for a stored QCM session."""
    summary = local_store.get_ai_practice_session_summary(session_id)
    questions = local_store.get_ai_practice_session(session_id)
    if summary is None:
        ui.notify("Session IA introuvable", type="warning")
        return
    if not questions:
        ui.notify("Cette session ne contient aucune question", type="warning")
        return

    rows = build_correction_rows(questions, summary)
    state = {"errors_only": False}
    statuses = {
        "correct": ("Correcte", "check_circle", "text-green-700 dark:text-green-400"),
        "incorrect": ("Incorrecte", "cancel", "text-red-700 dark:text-red-400"),
        "unanswered": ("Sans réponse", "help", "text-amber-700 dark:text-amber-400"),
        None: ("À évaluer", "pending", "text-slate-600 dark:text-slate-300"),
    }

    with ui.dialog() as dialog, ui.card().classes("w-[860px] max-w-[96vw] p-5"):
        score_text, counts_text = format_correction_summary(summary)
        ui.label(score_text).classes("text-xl font-semibold")
        ui.label(counts_text).classes("text-sm text-slate-600 dark:text-slate-300 mb-3")
        errors_toggle = ui.checkbox("Afficher uniquement les erreurs", value=False).props("dense")
        question_list = ui.column().classes("w-full gap-2 mt-2")

        def _render_rows() -> None:
            question_list.clear()
            with question_list:
                for row in filter_question_results(rows, state["errors_only"]):
                    label, icon, colour = statuses[row["status"]]
                    title = f"Question {row['position']} · {label}"
                    with ui.expansion(title, icon=icon).classes("w-full border rounded"):
                        ui.label(row["question"]["prompt"]).classes("font-medium whitespace-pre-wrap")
                        ui.label(label).classes(f"text-xs font-semibold mt-2 {colour}")
                        ui.label(f"Votre réponse : {row['response'] or '—'}").classes(
                            "text-sm whitespace-pre-wrap mt-2"
                        )
                        ui.label(f"Réponse correcte : {row['correct_answer'] or '—'}").classes(
                            "text-sm text-green-700 dark:text-green-400 whitespace-pre-wrap"
                        )
                        ui.label(f"Explication : {row['explanation']}").classes(
                            "text-sm text-slate-600 dark:text-slate-300 whitespace-pre-wrap mt-1"
                        )

        def _toggle_errors(event) -> None:
            state["errors_only"] = bool(event.value)
            _render_rows()

        def _back() -> None:
            dialog.close()
            on_back()

        def _replay() -> None:
            new_id = replay_qcm_session(session_id)
            if new_id is None:
                return
            dialog.close()
            on_replay(new_id)

        errors_toggle.on_value_change(_toggle_errors)
        _render_rows()
        with ui.row().classes("w-full justify-between mt-5"):
            ui.button("Retour", on_click=_back).props("flat")
            ui.button("Rejouer exactement", icon="replay", on_click=_replay).props("color=primary unelevated")
    dialog.open()


def open_qcm_session(
    session_id: int,
    on_complete: Callable[[int], None],
    on_back: Callable[[], None],
) -> None:
    """Open an immutable stored QCM session one question at a time."""
    questions = local_store.get_ai_practice_session(session_id)
    if not questions:
        ui.notify("Cette session ne contient aucune question", type="warning")
        return

    answers = latest_response_by_question(questions)
    persisted_answers = {
        int(question["id"]): str(_latest_attempt(question).get("response") or "")
        for question in questions
        if _latest_attempt(question) is not None
    }
    state = {"index": 0}
    with ui.dialog() as dialog, ui.card().classes("w-[760px] max-w-[96vw] p-5"):
        ui.label(f"Session IA #{session_id}").classes("text-lg font-semibold")
        progress = ui.label().classes("text-xs text-slate-500 mb-3")
        body = ui.column().classes("w-full")
        actions = ui.row().classes("w-full justify-between gap-2 mt-4")

        def _close() -> None:
            dialog.close()
            on_back()

        def _response(question: dict, control) -> str:
            if _is_open(question):
                return str(control.value or "").strip()
            return ", ".join(choice for choice, box in control if box.value)

        def _save(question: dict, response: str) -> None:
            is_open = _is_open(question)
            correct = None if is_open else _same_closed_answer(response, question.get("answer", ""), question.get("choices") or [])
            save_response_once(
                persisted_answers,
                question["id"],
                response,
                lambda: local_store.record_ai_practice_attempt(
                    session_id=session_id,
                    question_id=question["id"],
                    response=response,
                    is_correct=correct,
                    score_percent=None if is_open else (100.0 if correct else 0.0),
                    finalize_session=False,
                ),
            )

        def _render() -> None:
            body.clear()
            actions.clear()
            question = questions[state["index"]]
            progress.set_text(f"Question {state['index'] + 1} sur {len(questions)}")
            with body:
                with ui.row().classes("w-full items-start justify-between"):
                    ui.label(question["prompt"]).classes("font-medium whitespace-pre-wrap")
                    ui.button(
                        "Ancrer",
                        on_click=lambda qid=question["id"]: (
                            local_store.set_ai_practice_anchor(qid),
                            ui.notify("Question ajoutée aux ancrages", type="positive"),
                        ),
                    ).props("flat dense color=primary")
                if _is_open(question):
                    control = ui.textarea("Votre réponse", value=answers[question["id"]]).props(
                        "outlined autogrow"
                    ).classes("w-full")
                else:
                    selected = {_norm(value) for value in answers[question["id"]].split(",") if value.strip()}
                    control = [
                        (choice, ui.checkbox(choice, value=_norm(choice) in selected).props("dense"))
                        for choice in question.get("choices") or []
                    ]

            def _previous() -> None:
                answers[question["id"]] = _response(question, control)
                state["index"] -= 1
                _render()

            def _advance() -> None:
                response = _response(question, control)
                answers[question["id"]] = response
                try:
                    _save(question, response)
                except Exception as exc:
                    ui.notify(f"Échec de l'enregistrement : {exc}. Réessayez.", type="negative")
                    return
                state["index"] += 1
                _render()

            def _finish() -> None:
                response = _response(question, control)
                answers[question["id"]] = response
                if any(not str(answers[item["id"]]).strip() for item in questions):
                    ui.notify("Répondez à toutes les questions avant la correction.", type="warning")
                    return
                try:
                    _save(question, response)
                    local_store.finalize_ai_practice_session(session_id)
                    record_ai_practice_mastery(session_id)
                except Exception as exc:
                    ui.notify(f"Échec de l'enregistrement : {exc}. Réessayez.", type="negative")
                    return
                dialog.close()
                ui.notify("Réponses enregistrées dans l'historique", type="positive")
                on_complete(session_id)

            with actions:
                ui.button("Fermer", on_click=_close).props("flat")
                with ui.row().classes("gap-2"):
                    if state["index"]:
                        ui.button("Précédent", on_click=_previous).props("flat")
                    if state["index"] < len(questions) - 1:
                        ui.button("Suivant", on_click=_advance).props("color=primary unelevated")
                    else:
                        ui.button("Corriger mes réponses", on_click=_finish).props("color=primary unelevated")

        _render()
    dialog.open()
