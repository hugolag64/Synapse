"""JSON API for the Node QCM reader and correction screens."""

from __future__ import annotations

import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.core.practice.mastery import record_ai_practice_mastery
from backend.core.practice.attempt_service import (
    record_error_signals_for_attempt,
    score_and_record_closed_attempt,
)
from backend.core.practice.scoring import score_closed_attempt
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


def _record_error_signals(attempt_id: int, question_id: int, propositions: list[dict]) -> None:
    """Compatibility wrapper for older callers; the service is canonical."""
    record_error_signals_for_attempt(
        attempt_id=attempt_id,
        question_id=question_id,
        question=None,
        propositions=propositions,
    )


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
        import_service.assert_verified_exam(exam)
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


def _correction_payload(session_id: int, summary: dict) -> dict:
    """Construit la correction d'une session déjà répondue, sans effet de bord.

    Partagé avec la finalisation : celle-ci enregistre la maîtrise et clôt la
    session, cette lecture ne fait ni l'un ni l'autre. Sans elle, la correction
    n'existait qu'en retour de `POST /complete` et ne pouvait pas être rouverte.
    """
    questions = local_store.get_ai_practice_session(session_id)
    current = local_store.get_ai_practice_session_summary(session_id)
    rows = build_correction_rows(questions, current)
    latest_attempts = {
        int(attempt["question_id"]): int(attempt["id"])
        for attempt in (current or {}).get("latest_attempts", [])
    }
    for row in rows:
        correction = row.get("question", {}).get("correction")
        if correction:
            row["correction"] = correction
        attempt_id = latest_attempts.get(int(row["question"]["id"]))
        if attempt_id is not None:
            row["propositions"] = local_store.get_ai_practice_attempt_propositions(attempt_id)
    return {
        "session": summary,
        "rows": rows,
        "follow_up": _follow_up(session_id, dict(current or summary), rows),
    }


@router.get("/sessions/{session_id}")
def get_session(session_id: int) -> dict:
    return _session_payload(session_id)


@router.get("/sessions/{session_id}/correction")
def get_correction(session_id: int) -> dict:
    """Relit la correction d'une session sans la finaliser ni rejouer la maîtrise."""
    summary = local_store.get_ai_practice_session_summary(session_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Session QCM introuvable")
    return _correction_payload(session_id, {key: value for key, value in dict(summary).items() if key != "latest_attempts"})


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
    uness = question.get("uness") or (question.get("import_metadata") or {}).get("uness") or {}
    q_images = (uness.get("question") or {}).get("images") or []
    dp_images = ((uness.get("exam") or {}).get("dp_context") or {}).get("images") or []
    images = []
    seen = set()
    for img in list(q_images) + list(dp_images):
        lp = str(img.get("local_path") or "").strip()
        su = str(img.get("source_url") or "").strip()
        key = (lp, su)
        if key not in seen:
            seen.add(key)
            images.append(img)
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
    is_open = str(question.get("question_kind", "")).lower() == "open"
    scored = None
    if not is_open:
        _, scored = score_and_record_closed_attempt(
            session_id=session_id,
            question_id=payload.question_id,
            question=question,
            response=payload.response,
            finalize_session=False,
        )
        return {"ok": True, "score_mode": scored.score_mode}

    local_store.record_ai_practice_attempt(
        session_id=session_id,
        question_id=payload.question_id,
        response=payload.response,
        is_correct=None,
        score_percent=None,
        score_mode="",
        score_reason="",
        finalize_session=False,
    )
    return {"ok": True, "score_mode": ""}


@router.post("/sessions/{session_id}/complete")
def complete_session(session_id: int) -> dict:
    summary = local_store.finalize_ai_practice_session(session_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Session QCM introuvable")
    if summary.get("missing_positions"):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Toutes les questions doivent être corrigées avant la finalisation.",
                "missing_positions": summary["missing_positions"],
            },
        )
    record_ai_practice_mastery(session_id)
    return _correction_payload(session_id, summary)


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
