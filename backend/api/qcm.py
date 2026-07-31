"""JSON API for the Node QCM reader and correction screens."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.core.practice.mastery import record_ai_practice_mastery
from backend.core.reviews import local_store
from backend.core.uness import import_service
from backend.core.uness.import_service import (
    count_disagreements,
    import_uness_exam,
    load_local_exam,
)
from frontend.components.qcm_replay import _same_closed_answer, build_correction_rows

router = APIRouter(prefix="/api/qcm", tags=["qcm"])


class AttemptPayload(BaseModel):
    question_id: int
    response: str = ""


class FollowUpPayload(BaseModel):
    action: str
    question_id: int | None = None


class UnessImportPayload(BaseModel):
    path: str
    verify: bool = True


@router.post("/uness/import-directory")
def import_uness_directory() -> dict:
    """Scan the local verified ChatGPT output directory."""
    return import_service.import_verified_directory()


def _follow_up(session_id: int, summary: dict, rows: list[dict]) -> dict | None:
    score = summary.get("score_percent")
    if score is None or float(score) >= 70 or local_store.get_ai_practice_failure_streak(session_id) < 2:
        return None
    failed = [row for row in rows if row.get("status") in {"incorrect", "unanswered"}]
    if not failed:
        return None
    first = failed[0]
    return {
        "eligible": True,
        "failure_streak": local_store.get_ai_practice_failure_streak(session_id),
        "question_id": int(first["question"]["id"]),
        "question_prompt": first["question"].get("prompt", ""),
        "context": "OIC" if str(summary.get("practice_kind", "")).lower() == "oic" else "item",
    }


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


@router.post("/uness/import")
def import_uness(payload: UnessImportPayload) -> dict:
    """Import a verified JSON artifact from the local UNESS inbox only."""
    if not payload.verify:
        raise HTTPException(status_code=400, detail="Un examen UNESS doit être vérifié avant import")
    try:
        exam = load_local_exam(payload.path)
        session_id = import_uness_exam(exam)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Fichier UNESS introuvable") from exc
    except (PermissionError, ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "session_id": session_id,
        "questions": len(exam.questions),
        "disagreements": count_disagreements(exam),
    }


@router.get("/sessions/{session_id}")
def get_session(session_id: int) -> dict:
    return _session_payload(session_id)


@router.get("/sessions/{session_id}/questions/{question_id}/images/{image_index}")
def get_uness_question_image(
    session_id: int,
    question_id: int,
    image_index: int,
) -> FileResponse:
    """Serve an imported local visual without exposing arbitrary filesystem paths."""
    questions = local_store.get_ai_practice_session(session_id)
    question = next((item for item in questions if int(item["id"]) == question_id), None)
    if question is None:
        raise HTTPException(status_code=404, detail="Question QCM introuvable")
    images = ((question.get("uness") or {}).get("question") or {}).get("images") or []
    if image_index < 0 or image_index >= len(images):
        raise HTTPException(status_code=404, detail="Image UNESS introuvable")
    raw_path = str(images[image_index].get("local_path") or "").strip()
    if not raw_path:
        raise HTTPException(status_code=404, detail="Image UNESS locale introuvable")
    try:
        candidate = import_service.resolve_local_media_path(raw_path)
    except (FileNotFoundError, PermissionError):
        raise HTTPException(
            status_code=404,
            detail="Image UNESS locale introuvable",
        ) from None
    return FileResponse(candidate)


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
    current = local_store.get_ai_practice_session_summary(session_id)
    rows = build_correction_rows(questions, current)
    for row in rows:
        correction = row.get("question", {}).get("correction")
        if correction:
            row["correction"] = correction
    return {
        "session": summary,
        "rows": rows,
        "follow_up": _follow_up(session_id, dict(current or summary), rows),
    }


@router.post("/sessions/{session_id}/follow-up")
def follow_up(session_id: int, payload: FollowUpPayload) -> dict:
    summary = local_store.get_ai_practice_session_summary(session_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Session QCM introuvable")
    if payload.action == "anchor":
        if payload.question_id is None:
            raise HTTPException(status_code=400, detail="Question à ancrer manquante")
        local_store.set_ai_practice_anchor(payload.question_id)
        return {"ok": True, "message": "Question ajoutée aux ancrages"}
    if payload.action == "lacune":
        questions = local_store.get_ai_practice_session(session_id)
        failed = [q for q in questions if q.get("attempts") and q["attempts"][-1].get("is_correct") == 0]
        if not failed:
            raise HTTPException(status_code=400, detail="Aucune erreur exploitable pour créer une lacune")
        detail = "Échecs répétés sur : " + "; ".join(q.get("prompt", "")[:120] for q in failed[:3])
        weak_id = local_store.add_weak_point_full(
            course_id=summary.get("course_id", ""),
            detail=detail,
            course_title=summary.get("course_title", ""),
            item_number=summary.get("item_number", ""),
            category="OIC" if str(summary.get("practice_kind", "")).lower() == "oic" else "connaissance",
            severity=3,
            source_type="qcm",
            source_session_id=session_id,
        )
        return {"ok": True, "message": "Fiche lacune créée", "weak_point_id": weak_id}
    if payload.action == "ignore":
        return {"ok": True, "message": "Suggestion ignorée"}
    raise HTTPException(status_code=400, detail="Action de suivi inconnue")


@router.post("/sessions/{session_id}/replay")
def replay_session(session_id: int) -> dict:
    try:
        return {"session_id": local_store.replay_ai_practice_session(session_id)}
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
