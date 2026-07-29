"""JSON API for the Node QCM reader and correction screens."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.practice.mastery import record_ai_practice_mastery
from backend.core.reviews import local_store
from frontend.components.qcm_replay import _same_closed_answer, build_correction_rows

router = APIRouter(prefix="/api/qcm", tags=["qcm"])


class AttemptPayload(BaseModel):
    question_id: int
    response: str = ""


def _session_payload(session_id: int) -> dict:
    summary = local_store.get_ai_practice_session_summary(session_id)
    questions = local_store.get_ai_practice_session(session_id)
    if summary is None or not questions:
        raise HTTPException(status_code=404, detail="Session QCM introuvable")
    return {
        "session": {key: value for key, value in dict(summary).items() if key != "latest_attempts"},
        "questions": [dict(question) for question in questions],
        "answers": {
            str(question["id"]): next(
                (
                    str(attempt.get("response") or "")
                    for attempt in reversed(question.get("attempts") or [])
                    if str(attempt.get("response") or "").strip()
                ),
                "",
            )
            for question in questions
        },
    }


@router.get("/sessions/{session_id}")
def get_session(session_id: int) -> dict:
    return _session_payload(session_id)


@router.post("/sessions/{session_id}/attempts")
def save_attempt(session_id: int, payload: AttemptPayload) -> dict:
    questions = local_store.get_ai_practice_session(session_id)
    question = next((row for row in questions if int(row["id"]) == payload.question_id), None)
    if question is None:
        raise HTTPException(status_code=404, detail="Question QCM introuvable")
    local_store.record_ai_practice_attempt(
        session_id=session_id,
        question_id=payload.question_id,
        response=payload.response,
        is_correct=None if str(question.get("question_kind", "")).lower() == "open" else _same_closed_answer(
            payload.response, question.get("answer", ""), question.get("choices") or []
        ),
        score_percent=(
            None
            if str(question.get("question_kind", "")).lower() == "open"
            else (100.0 if _same_closed_answer(payload.response, question.get("answer", ""), question.get("choices") or []) else 0.0)
        ),
        finalize_session=False,
    )
    return {"ok": True}


@router.post("/sessions/{session_id}/complete")
def complete_session(session_id: int) -> dict:
    summary = local_store.finalize_ai_practice_session(session_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Session QCM introuvable")
    record_ai_practice_mastery(session_id)
    questions = local_store.get_ai_practice_session(session_id)
    return {
        "session": summary,
        "rows": build_correction_rows(questions, local_store.get_ai_practice_session_summary(session_id)),
    }


@router.post("/sessions/{session_id}/replay")
def replay_session(session_id: int) -> dict:
    try:
        return {"session_id": local_store.replay_ai_practice_session(session_id)}
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
