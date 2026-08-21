"""Worker de fond : scan des conférences éligibles, soumission, polling et
application du résultat de l'analyse Batch audio-informée."""
from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path

from loguru import logger

from backend.core.ai import batch_client
from backend.core.ai.gemini_client import GeminiClientError
from backend.core.conferences.analysis_prompt import (
    PROMPT_VERSION,
    ConferenceQuestionSnapshot,
    build_conference_analysis_request,
    parse_conference_analysis_response,
)
from backend.core.reviews import local_store
from backend.core.uness.item_classifier import candidate_items_for_college

_MODEL_ID = "gemini-flash-lite"
_POLL_INTERVAL_SECONDS = 900  # 15 min, borné par le cycle de fond (5 min)


def _idempotency_key(conference_id: int, uness_session_id: int, audio_hash: str) -> str:
    raw = f"{audio_hash}:{conference_id}:{uness_session_id}:{_MODEL_ID}:{PROMPT_VERSION}"
    return f"{audio_hash}:{hashlib.sha256(raw.encode()).hexdigest()}"


def scan_and_queue_conference_analyses() -> int:
    created = 0
    for conference in local_store.list_conferences_eligible_for_analysis():
        key = _idempotency_key(conference["id"], conference["uness_session_id"], conference["audio_hash"])
        job = local_store.create_conference_analysis_job(
            conference_id=conference["id"],
            uness_session_id=conference["uness_session_id"],
            model_id=_MODEL_ID,
            idempotency_key=key,
            prompt_version=PROMPT_VERSION,
        )
        if job["status"] == "pending":
            created += 1
    return created


def submit_pending_conference_analysis_jobs(*, limit: int = 5, client=None) -> dict[str, int]:
    client = client or batch_client
    counts = {"claimed": 0, "submitted": 0, "failed": 0}
    for job in local_store.claim_pending_conference_analysis_jobs(limit=limit):
        counts["claimed"] += 1
        try:
            conference = local_store.get_conference(job["conference_id"])
            annale = local_store.get_uness_annale(job["uness_session_id"])
            questions = local_store.list_uness_annale_questions_for_analysis(job["uness_session_id"])
            if not questions:
                raise GeminiClientError("Dossier UNESS sans question importée")

            uploaded = client.upload_audio_file(Path(conference["audio_path"]))
            snapshots = [
                ConferenceQuestionSnapshot(
                    question_id=str(q["question_id"]), enonce=q["prompt"], official_answer=q["answer"],
                    official_item=q["official_item"], official_rank=q["official_rank"],
                )
                for q in questions
            ]
            request_body = build_conference_analysis_request(
                audio_file=uploaded, college_label=(annale or {}).get("matiere", ""), questions=snapshots,
            )
            handle = client.create_batch_job(_MODEL_ID, request_body)
            next_poll = (
                datetime.datetime.now().astimezone() + datetime.timedelta(seconds=_POLL_INTERVAL_SECONDS)
            ).isoformat(timespec="seconds")
            local_store.mark_conference_analysis_job_submitted(
                job["id"], provider_job_name=handle.name, next_poll_at=next_poll,
            )
            counts["submitted"] += 1
        except Exception as exc:  # noqa: BLE001 - une conférence en échec ne bloque pas les autres
            logger.warning(f"Soumission de l'analyse conférence {job['id']} échouée : {exc}")
            local_store.fail_conference_analysis_job(job["id"], error=str(exc))
            counts["failed"] += 1
    return counts


def _extract_response_text(status: "batch_client.BatchJobStatus") -> str:
    if status.inlined_responses:
        parts = status.inlined_responses[0]["response"]["candidates"][0]["content"]["parts"]
        return "".join(part.get("text", "") for part in parts)
    if status.responses_file_name:
        raw = batch_client.download_batch_results(status.responses_file_name)
        first_line = raw.splitlines()[0]
        payload = json.loads(first_line)
        parts = payload["response"]["candidates"][0]["content"]["parts"]
        return "".join(part.get("text", "") for part in parts)
    raise GeminiClientError("Job Batch terminé sans résultat exploitable")


def _apply_result(job: dict, questions: list[dict], response_text: str) -> str:
    known_ids = {str(q["question_id"]) for q in questions}
    college_label = (local_store.get_uness_annale(job["uness_session_id"]) or {}).get("matiere", "")
    candidates = {c["item"] for c in candidate_items_for_college(college_label)}
    candidate_items_by_question = {qid: candidates for qid in known_ids}

    parsed = parse_conference_analysis_response(
        response_text, known_question_ids=known_ids, candidate_items=candidate_items_by_question,
    )

    analysis = local_store.record_conference_analysis(
        conference_id=job["conference_id"], uness_session_id=job["uness_session_id"],
        batch_job_id=job["id"], model_id=job["model_id"], prompt_version=job["prompt_version"],
        summary_text=parsed.summary,
    )

    any_needs_admin = False
    for question_id_str, result in parsed.questions.items():
        question_id = int(question_id_str)
        if result.item_number and not result.item_needs_admin:
            local_store.apply_conference_item_classification(
                question_id, result.item_number,
                confidence=result.item_confidence, rationale=result.item_rationale,
            )
        elif result.item_needs_admin:
            any_needs_admin = True

        if result.rank and not result.rank_needs_admin:
            local_store.apply_conference_rank_result(
                question_id, rank=result.rank, confidence=result.rank_confidence,
                evidence=[], rationale=result.rank_rationale,
            )
        elif result.rank_needs_admin:
            any_needs_admin = True

        local_store.record_conference_question_analysis(
            conference_analysis_id=analysis["id"], question_id=question_id,
            verdict=result.verdict, confidence=result.verdict_confidence,
            rationale=result.verdict_rationale, transcript_excerpt=result.transcript_excerpt,
        )

    if not parsed.questions:
        return "failed"
    if any_needs_admin:
        return "needs_admin"
    if len(parsed.questions) < len(known_ids):
        return "partial"
    return "succeeded"


def _log_batch_usage(job: dict, status: "batch_client.BatchJobStatus") -> None:
    """Trace le coût dans ai_usage_logs sans nouvelle colonne : le mode batch et le job
    Batch Gemini sont portés par `context` (JSON), pas par le schéma existant, pour éviter
    d'étendre ai_usage_logs pour ce seul chantier."""
    usage = {}
    if status.inlined_responses:
        usage = status.inlined_responses[0].get("response", {}).get("usageMetadata", {})
    local_store.record_ai_usage(
        task="conference_analysis",
        model=job["model_id"],
        input_tokens=int(usage.get("promptTokenCount") or 0),
        output_tokens=int(usage.get("candidatesTokenCount") or 0),
        cost_usd=0.0,  # pas de registre de prix Batch/audio dans ce chantier (YAGNI)
        context=json.dumps({
            "execution_mode": "batch", "conference_id": job["conference_id"],
            "batch_job_id": job["id"], "provider_job_name": job["provider_job_name"],
        }),
    )


def poll_running_conference_analysis_jobs(*, limit: int = 10, client=None) -> dict[str, int]:
    client = client or batch_client
    counts = {"polled": 0, "succeeded": 0, "partial": 0, "needs_admin": 0, "not_ready": 0, "failed": 0}
    for job in local_store.list_conference_analysis_jobs_due_for_poll(limit=limit):
        counts["polled"] += 1
        try:
            status = client.get_batch_job(job["provider_job_name"])
            if not status.done:
                next_poll = (
                    datetime.datetime.now().astimezone() + datetime.timedelta(seconds=_POLL_INTERVAL_SECONDS)
                ).isoformat(timespec="seconds")
                local_store.mark_conference_analysis_job_polled(job["id"], next_poll_at=next_poll)
                counts["not_ready"] += 1
                continue
            if status.state == "JOB_STATE_FAILED":
                raise GeminiClientError(status.error or "Job Batch en échec")

            response_text = _extract_response_text(status)
            questions = local_store.list_uness_annale_questions_for_analysis(job["uness_session_id"])
            final_status = _apply_result(job, questions, response_text)
            if final_status == "failed":
                raise GeminiClientError("Aucun résultat exploitable dans la réponse Batch")
            local_store.complete_conference_analysis_job(job["id"], status=final_status, result_path="")
            _log_batch_usage(job, status)
            counts[final_status] += 1
        except Exception as exc:  # noqa: BLE001 - isole une conférence en échec des autres
            logger.warning(f"Analyse conférence {job['id']} : {exc}")
            local_store.fail_conference_analysis_job(job["id"], error=str(exc))
            counts["failed"] += 1
    return counts


def run_conference_analysis_cycle(*, client=None) -> dict[str, int]:
    created = scan_and_queue_conference_analyses()
    submitted = submit_pending_conference_analysis_jobs(client=client)
    polled = poll_running_conference_analysis_jobs(client=client)
    return {
        "created": created,
        **{f"submit_{k}": v for k, v in submitted.items()},
        **{f"poll_{k}": v for k, v in polled.items()},
    }
