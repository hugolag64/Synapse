"""Pure view models for replaying and correcting stored QCM sessions."""

from __future__ import annotations

import re


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
