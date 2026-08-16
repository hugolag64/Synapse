"""Background orchestration for question-level UNESS rank inference."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from loguru import logger

from backend.core.ai.tasks import infer_uness_ranks
from backend.core.practice.rank_service import resolve_rank
from backend.core.reviews import local_store
from backend.core.uness.rank_inference import (
    build_uness_rank_prompt,
    parse_uness_rank_response,
)


def _course_value(course: Any, name: str) -> str:
    if isinstance(course, Mapping):
        return str(course.get(name) or "").strip()
    return str(getattr(course, name, "") or "").strip()


def _question_payload(job: Mapping[str, Any]) -> dict[str, Any]:
    metadata = job.get("import_metadata") or {}
    uness = metadata.get("uness") if isinstance(metadata, Mapping) else {}
    question = uness.get("question") if isinstance(uness, Mapping) else {}
    question = question if isinstance(question, Mapping) else {}
    return {
        "id": str(job.get("question_external_id") or "").strip(),
        "prompt": str(job.get("prompt") or "").strip(),
        "choices": job.get("choices") or [],
        "answer": str(job.get("answer") or ""),
        "explanation": str(job.get("explanation") or ""),
        "item_numbers": list(question.get("item_numbers") or [job.get("item_number")]),
    }


def _course_ids_by_item(courses: Iterable[Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for course in courses or ():
        item_number = _course_value(course, "item_number")
        course_id = _course_value(course, "id")
        if item_number and course_id and course_id not in result[item_number]:
            result[item_number].append(course_id)
    return result


def _default_courses() -> list[Any]:
    from backend.state.store import data_store

    return list(getattr(data_store, "cours", []) or [])


def scan_and_queue_missing_ranks() -> list[dict]:
    return local_store.scan_uness_rank_jobs()


def run_uness_rank_jobs(
    *,
    limit: int = 10,
    courses: Iterable[Any] | None = None,
    service: Any = None,
    worker_id: str = "uness-rank-worker",
) -> dict[str, int]:
    """Run a bounded batch, isolating one failed item from the others."""
    counts = {
        "scanned": len(scan_and_queue_missing_ranks()),
        "claimed": 0,
        "resolved": 0,
        "needs_admin": 0,
        "needs_oic": 0,
        "failed": 0,
    }
    claimed = local_store.claim_uness_rank_jobs(limit=limit, worker_id=worker_id)
    counts["claimed"] = len(claimed)
    if not claimed:
        return counts

    course_ids_by_item = _course_ids_by_item(_default_courses() if courses is None else courses)
    by_item: dict[str, list[dict]] = defaultdict(list)
    for job in claimed:
        by_item[str(job.get("item_number") or "").strip()].append(job)

    for item_number, item_jobs in by_item.items():
        try:
            oics = local_store.get_lisa_oic_for_item(item_number, course_ids_by_item.get(item_number, []))
            if not oics:
                for job in item_jobs:
                    local_store.mark_uness_rank_job_needs_oic(job["id"])
                    counts["needs_oic"] += 1
                continue

            questions = [_question_payload(job) for job in item_jobs]
            prompt = build_uness_rank_prompt(item_number, questions, oics)
            response = infer_uness_ranks(prompt, service=service)
            inferred = parse_uness_rank_response(
                response.text,
                [question["id"] for question in questions],
            )
            for job in item_jobs:
                candidate = inferred.get(str(job["question_external_id"]))
                if candidate is None:
                    local_store.record_uness_rank_result(
                        job["id"],
                        raw_response=response.text,
                        status="needs_admin",
                    )
                    counts["needs_admin"] += 1
                    continue
                decision = resolve_rank(
                    gemini_rank=candidate.rank,
                    gemini_confidence=candidate.confidence,
                    gemini_evidence=candidate.oic_codes,
                    gemini_rationale=candidate.rationale,
                    gemini_ambiguous=candidate.ambiguous,
                )
                if decision.status != "resolved":
                    local_store.record_uness_rank_result(
                        job["id"],
                        rank=candidate.rank,
                        confidence=candidate.confidence,
                        ambiguous=candidate.ambiguous,
                        oic_codes=list(candidate.oic_codes),
                        rationale=candidate.rationale,
                        raw_response=response.text,
                        status="needs_admin",
                    )
                    counts["needs_admin"] += 1
                    continue
                local_store.record_uness_rank_result(
                    job["id"],
                    rank=candidate.rank,
                    confidence=candidate.confidence,
                    ambiguous=False,
                    oic_codes=list(candidate.oic_codes),
                    rationale=candidate.rationale,
                    raw_response=response.text,
                    status="needs_admin",
                )
                local_store.accept_uness_rank_job(job["id"])
                counts["resolved"] += 1
        except Exception as exc:  # noqa: BLE001 - one item batch must not stop the queue
            logger.warning("Inférence de rang UNESS ignorée pour l'item {} : {}", item_number, exc)
            for job in item_jobs:
                try:
                    local_store.record_uness_rank_failure(job["id"], error=str(exc))
                except Exception as record_exc:  # noqa: BLE001
                    logger.warning("Échec de persistance du job de rang {} : {}", job["id"], record_exc)
                counts["failed"] += 1
    return counts


def run_uness_rank_cycle(*, limit: int = 10, courses: Iterable[Any] | None = None, service: Any = None) -> dict[str, int]:
    return run_uness_rank_jobs(limit=limit, courses=courses, service=service)
