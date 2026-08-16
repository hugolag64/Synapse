"""Local daily queue built from questions already present in SQLite.

This module deliberately has no AI dependency. It turns existing draft
sessions into a small, deterministic practice session so paid content is
played before any new content is generated.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Callable

from backend.core.knowledge.retention import project_retention
from backend.core.practice.models import PracticeDifficulty, PracticeKind, PracticeSessionSpec
from backend.core.reviews import local_store

DAILY_QUEUE_MODEL = "local-daily-queue-v1"


def _draft_questions() -> list[dict]:
    """Return unanswered questions from draft sessions, oldest source first."""
    with local_store._conn() as connection:
        rows = connection.execute(
            """
            SELECT q.*, s.id AS source_session_id, s.course_title AS source_title,
                   s.created_at AS source_created_at,
                   COALESCE(
                       NULLIF(TRIM(q.item_number), ''),
                       (SELECT qi.item_number
                          FROM ai_practice_question_items qi
                         WHERE qi.question_id = q.id
                         ORDER BY qi.item_number LIMIT 1),
                       ''
                   ) AS resolved_item_number
              FROM ai_practice_sessions s
              JOIN ai_practice_session_questions sq ON sq.session_id = s.id
              JOIN ai_practice_questions q ON q.id = sq.question_id
             WHERE s.completion_state = 'draft'
               AND s.model != ?
               AND NOT EXISTS (
                   SELECT 1
                     FROM ai_practice_attempts a
                    WHERE a.session_id = s.id
                      AND a.question_id = q.id
                      AND (
                          TRIM(COALESCE(a.response, '')) NOT IN ('', '[]')
                          OR a.score_percent IS NOT NULL
                      )
               )
             ORDER BY s.created_at ASC, s.id ASC, sq.position ASC
            """,
            (DAILY_QUEUE_MODEL,),
        ).fetchall()

    result = []
    for row in rows:
        value = dict(row)
        try:
            value["choices"] = json.loads(value.pop("choices_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            value["choices"] = []
        try:
            value["source_refs"] = json.loads(value.pop("source_refs_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            value["source_refs"] = []
        try:
            value["import_metadata"] = json.loads(value.pop("import_metadata_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            value["import_metadata"] = {}
        value["item_number"] = str(value.pop("resolved_item_number") or "").strip()
        result.append(value)
    return result


def _retention_for_item(item_number: str, resolver: Callable | None = None) -> tuple[float, float]:
    """Return (retention projected at J+7, stability), with a safe fallback."""
    if resolver is None:
        try:
            from backend.core.reviews.mastery import get_item_mastery
            snapshot = get_item_mastery(item_number)
        except Exception:
            snapshot = None
    else:
        snapshot = resolver(item_number)

    if snapshot is None or snapshot.retention_score is None:
        return 25.0, 0.0
    stability = float(snapshot.retention_stability_days or 0.0)
    return project_retention(int(snapshot.retention_score), stability, 7), stability


def build_daily_question_queue(
    *, limit: int = 5, retention_resolver: Callable | None = None,
) -> list[dict]:
    """Rank existing draft questions by frequency × deficit × availability."""
    candidates = _draft_questions()
    if not candidates or limit <= 0:
        return []

    item_counts = Counter(row["item_number"] for row in candidates if row["item_number"])
    scored = []
    retention_cache: dict[str, tuple[float, float]] = {}
    frequency_cache: dict[str, dict] = {}
    for row in candidates:
        item_number = row["item_number"]
        if item_number not in retention_cache:
            retention_cache[item_number] = _retention_for_item(item_number, retention_resolver)
        projected_retention, stability = retention_cache[item_number]
        if item_number not in frequency_cache:
            frequency_cache[item_number] = local_store.get_ednpro_item_frequency(item_number) or {}
        frequency = frequency_cache[item_number]
        frequency_sessions = max(0, int(frequency.get("session_count") or 0))
        expected_questions = max(0, int(frequency.get("question_count") or 0))
        available_questions = item_counts.get(item_number, 0)
        availability = 1.0 if expected_questions <= 0 else min(1.0, available_questions / expected_questions)
        deficit = max(0.0, 100.0 - projected_retention)
        score = round(frequency_sessions * deficit * availability, 2)
        scored.append({
            **row,
            "priority_score": score,
            "priority_factors": {
                "frequency_sessions": frequency_sessions,
                "projected_retention_j7": round(projected_retention, 1),
                "retention_stability_days": round(stability, 1),
                "deficit": round(deficit, 1),
                "availability": round(availability, 3),
            },
        })

    scored.sort(key=lambda row: (
        -row["priority_score"], str(row.get("item_number") or ""),
        str(row.get("source_created_at") or ""), int(row.get("id") or 0),
    ))
    return scored[: max(0, int(limit))]


def create_daily_queue_session(*, limit: int = 5) -> int | None:
    """Create one local session containing today's selected existing questions."""
    import datetime

    today = datetime.date.today().isoformat()
    with local_store._conn() as connection:
        existing = connection.execute(
            """SELECT id FROM ai_practice_sessions
               WHERE model = ? AND substr(created_at, 1, 10) = ?
               ORDER BY id DESC LIMIT 1""",
            (DAILY_QUEUE_MODEL, today),
        ).fetchone()
    if existing is not None:
        return int(existing["id"])

    queue = build_daily_question_queue(limit=limit)
    if not queue:
        return None
    item_numbers = tuple(dict.fromkeys(row["item_number"] for row in queue if row["item_number"]))
    questions = [
        {
            "prompt": row["prompt"], "kind": row["question_kind"],
            "choices": row["choices"], "answer": row["answer"],
            "explanation": row["explanation"], "source_refs": row["source_refs"],
            "item_numbers": (row["item_number"],) if row["item_number"] else (),
            "import_metadata": row["import_metadata"],
        }
        for row in queue
    ]
    open_count = sum(row["kind"] == "open" for row in questions)
    spec = PracticeSessionSpec(
        practice_kind=PracticeKind.QCM, total_questions=len(questions),
        open_questions=open_count, closed_questions=len(questions) - open_count,
        item_number=item_numbers[0] if item_numbers else "", item_numbers=item_numbers,
        course_title="Les 5 du jour", difficulty=PracticeDifficulty.EDN,
    )
    return local_store.create_ai_practice_session(
        spec=spec, questions=questions, model=DAILY_QUEUE_MODEL
    )
