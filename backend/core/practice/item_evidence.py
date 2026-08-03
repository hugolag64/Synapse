"""Question-level evidence aggregation for practice mastery."""

from __future__ import annotations

from collections import defaultdict

from backend.core.reviews import local_store


def get_session_item_evidence(session_id: int) -> dict[str, dict]:
    """Aggregate the latest scored attempts by explicit question-item links."""
    with local_store._conn() as con:
        rows = con.execute(
            """SELECT qi.item_number, sq.question_id, attempt.score_percent
               FROM ai_practice_session_questions sq
               JOIN ai_practice_question_items qi
                 ON qi.question_id = sq.question_id
               JOIN (
                 SELECT question_id, MAX(id) AS max_id
                 FROM ai_practice_attempts
                 WHERE session_id = ?
                   AND TRIM(COALESCE(response, '')) NOT IN ('', '[]')
                   AND score_percent IS NOT NULL
                 GROUP BY question_id
               ) latest ON latest.question_id = sq.question_id
               JOIN ai_practice_attempts attempt ON attempt.id = latest.max_id
               WHERE sq.session_id = ?
               ORDER BY qi.item_number, sq.position""",
            (session_id, session_id),
        ).fetchall()

    scores: dict[str, list[float]] = defaultdict(list)
    question_ids: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        item_number = str(row["item_number"] or "").strip()
        if not item_number:
            continue
        scores[item_number].append(float(row["score_percent"]))
        question_ids[item_number].append(int(row["question_id"]))

    return {
        item_number: {
            "score_percent": round(sum(values) / len(values), 2),
            "total_questions": len(values),
            "correct_answers": sum(value == 100.0 for value in values),
            "wrong_answers": sum(value < 100.0 for value in values),
            "question_ids": question_ids[item_number],
        }
        for item_number, values in scores.items()
    }
