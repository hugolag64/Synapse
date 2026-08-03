"""Pure view models for replaying and correcting stored QCM sessions."""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from nicegui import ui

from backend.core.practice.mastery import record_ai_practice_mastery
from backend.core.reviews import local_store


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _has_response(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return True
    return any(str(item).strip() for item in parsed) if isinstance(parsed, list) else True


def _closed_response_values(value: str, choices: list[str]) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        parsed = None
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    if any(_norm(text) == _norm(choice) for choice in choices):
        return [text]
    return [part.strip() for part in re.split(r"[,;|/]", text) if part.strip()]


def serialize_closed_response(selected_choices: list[str]) -> str:
    """Persist selected labels without losing commas contained in a choice."""
    selected = [str(choice).strip() for choice in selected_choices if str(choice).strip()]
    return json.dumps(selected, ensure_ascii=False) if selected else ""


def deserialize_closed_response(response: str, choices: list[str]) -> list[str]:
    """Restore JSON responses and legacy delimiter-separated response strings."""
    restored = []
    for value in _closed_response_values(response, choices):
        normalized = _norm(value)
        match = next((choice for choice in choices if normalized == _norm(choice)), None)
        if match is None and len(normalized) == 1:
            index = ord(normalized) - ord("a")
            if 0 <= index < len(choices):
                match = choices[index]
        if match is not None and match not in restored:
            restored.append(match)
    return restored


def _same_closed_answer(response: str, answer: str, choices: list[str]) -> bool:
    def _tokens(value: str) -> set[str]:
        result = set()
        for token in _closed_response_values(value, choices):
            normalized = _norm(token)
            for index, choice in enumerate(choices):
                letter = chr(ord("a") + index)
                if normalized in {letter, _norm(choice)}:
                    normalized = letter
                    break
            result.add(normalized)
        return result

    response_tokens = _tokens(response)
    return bool(response_tokens) and response_tokens == _tokens(answer)


def _is_open(question: dict) -> bool:
    return str(question.get("question_kind", question.get("kind", ""))).lower() == "open"


def build_question_result(question: dict, latest_attempt: dict | None) -> dict:
    choices = list(question.get("choices") or [])
    is_open = _is_open(question)
    raw_response = "" if latest_attempt is None else str(latest_attempt.get("response") or "")
    response = raw_response
    if not is_open and raw_response.lstrip().startswith("["):
        response = ", ".join(deserialize_closed_response(raw_response, choices))
    explicit_status = None if latest_attempt is None else latest_attempt.get("is_correct")
    if latest_attempt is None or not _has_response(raw_response):
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
    attempts = [
        attempt
        for attempt in question.get("attempts") or []
        if _has_response(attempt.get("response", ""))
    ]
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
    if not _has_response(response):
        return False
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
    if score is None:
        score_text = "Score non disponible"
    else:
        score_20 = round(float(score) / 5.0, 1)
        score_20_str = f"{score_20:g}".replace(".", ",")
        score_text = f"Note : {score_20_str}/20 ({score:g} %)"
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
        attempt = latest_attempts.get(int(question["id"]))
        result = build_question_result(question, attempt)
        propositions = (
            local_store.get_ai_practice_attempt_propositions(int(attempt["id"]))
            if attempt and attempt.get("id") is not None
            else []
        )
        rows.append({"question": question, "position": position, "propositions": propositions, **result})
    return rows


def replay_qcm_session(session_id: int) -> int | None:
    """Create an immutable replay and surface storage failures consistently."""
    try:
        return local_store.replay_ai_practice_session(session_id)
    except Exception as exc:
        ui.notify(str(exc), type="negative")
        return None


def session_action_keys(session: dict) -> tuple[str, ...]:
    """Return only the actions valid for a pending or completed session."""
    if session.get("status") == "completed" or session.get("completed_at") is not None:
        return ("correction", "replay")
    return ("resume",)


def open_chained_dialog(
    parent_slot,
    open_next: Callable[[], None],
    *,
    refresh: Callable[[], None] | None = None,
) -> None:
    """Open a chained dialog under a stable slot after any caller refresh."""
    if refresh is not None:
        refresh()
    with parent_slot:
        open_next()


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
                    uness = row["question"].get("uness") or {}
                    disagreements = [
                        proposition
                        for proposition in uness.get("propositions") or []
                        if proposition.get("statut") == "desaccord"
                    ]
                    title = f"Question {row['position']} · {label}"
                    if disagreements:
                        title = f"{title} · ⚠ Divergence UNESS"
                    with ui.expansion(title, icon=icon).classes("w-full border rounded"):
                        ui.label(row["question"]["prompt"]).classes("font-medium whitespace-pre-wrap")
                        ui.label(label).classes(f"text-xs font-semibold mt-2 {colour}")
                        exam_metadata = uness.get("exam") or {}
                        provenance = uness.get("provenance") or {}
                        source_url = str(provenance.get("source_url") or "").strip()
                        if source_url:
                            ui.label(f"Source : {source_url}").classes(
                                "text-xs text-slate-500 dark:text-slate-400 whitespace-pre-wrap mt-2"
                            )
                        identity = [
                            str(value).strip()
                            for value in (
                                exam_metadata.get("faculty"),
                                exam_metadata.get("level"),
                                exam_metadata.get("year"),
                            )
                            if value is not None and str(value).strip()
                        ]
                        if identity:
                            ui.label(" · ".join(identity)).classes(
                                "text-xs text-slate-500 dark:text-slate-400"
                            )
                        collected_at = str(provenance.get("collected_at") or "").strip()
                        collection_status = str(
                            provenance.get("collection_status") or ""
                        ).strip()
                        if collected_at or collection_status:
                            ui.label(
                                f"Collecté le {collected_at or '—'} · "
                                f"Statut : {collection_status or '—'}"
                            ).classes("text-xs text-slate-500 dark:text-slate-400")
                        ui.label(f"Votre réponse : {row['response'] or '—'}").classes(
                            "text-sm whitespace-pre-wrap mt-2"
                        )
                        ui.label(f"Réponse correcte : {row['correct_answer'] or '—'}").classes(
                            "text-sm text-green-700 dark:text-green-400 whitespace-pre-wrap"
                        )
                        ui.label(f"Explication : {row['explanation']}").classes(
                            "text-sm text-slate-600 dark:text-slate-300 whitespace-pre-wrap mt-1"
                        )
                        if disagreements:
                            ui.label("Divergence avec la correction officielle UNESS").classes(
                                "text-sm font-semibold text-amber-800 dark:text-amber-300 mt-2"
                            )
                            for proposition in disagreements:
                                comment = str(
                                    proposition.get("commentaire_desaccord") or ""
                                ).strip()
                                if comment:
                                    ui.label(comment).classes(
                                        "text-sm text-amber-800 dark:text-amber-300 whitespace-pre-wrap"
                                    )
                        question_metadata = uness.get("question") or {}
                        if question_metadata.get("support_visuel_seul"):
                            ui.label(
                                "Support visuel uniquement : l’interaction UNESS originale "
                                "n’est pas reconstruite."
                            ).classes(
                                "text-sm text-amber-800 dark:text-amber-300 whitespace-pre-wrap mt-2"
                            )
                        if question_metadata.get("verification_status") == "unsupported":
                            ui.label(
                                "⚠️ Vérification IA non disponible pour cette question — seule la "
                                "correction officielle UNESS est garantie exacte."
                            ).classes(
                                "text-sm text-amber-800 dark:text-amber-300 whitespace-pre-wrap mt-2"
                            )
                        for image in question_metadata.get("images") or []:
                            source = str(
                                image.get("local_path") or image.get("source_url") or ""
                            ).strip()
                            if not source:
                                continue
                            ui.image(source).classes("w-full max-h-80 object-contain rounded mt-2")
                            caption = str(
                                image.get("caption") or image.get("alt_text") or ""
                            ).strip()
                            if caption:
                                ui.label(caption).classes(
                                    "text-xs text-slate-500 dark:text-slate-400"
                                )
                        official = (row["question"].get("correction") or {}).get("official")
                        if isinstance(official, dict):
                            answers = ", ".join(str(answer) for answer in official.get("answer") or [])
                            availability = "" if official.get("available") else " (partielle)"
                            with ui.expansion("Correction officielle UNESS", icon="fact_check").classes(
                                "w-full mt-2"
                            ):
                                ui.label(
                                    f"Correction officielle UNESS{availability} : {answers or '—'}"
                                ).classes("text-sm text-slate-600 dark:text-slate-300 whitespace-pre-wrap")

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
            return serialize_closed_response([choice for choice, box in control if box.value])

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
                    selected = {
                        _norm(value)
                        for value in deserialize_closed_response(
                            answers[question["id"]], question.get("choices") or []
                        )
                    }
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
