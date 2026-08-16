"""Composition locale et déterministe des épreuves officielles."""

from __future__ import annotations

import datetime as dt
import random
from collections import defaultdict
from typing import Literal

from backend.core.practice.models import PracticeDifficulty, PracticeKind, PracticeSessionSpec
from backend.core.reviews import local_store

ExamFormat = Literal["dp", "series", "mixed"]

DEFAULT_DURATIONS = {"dp": 3 * 60 * 60, "series": 90 * 60, "mixed": 2 * 60 * 60}


def _candidate_weight(candidate: dict) -> float:
    frequency = min(3.0, float(candidate.get("frequency_question_count") or 0) / 10.0)
    errors = min(4.0, float(candidate.get("error_count") or 0) * 0.75)
    last_date = str(candidate.get("last_practice_date") or "").strip()
    age = 1.0
    if last_date:
        try:
            days = max(0, (dt.date.today() - dt.date.fromisoformat(last_date[:10])).days)
            age += min(3.0, days / 90.0)
        except ValueError:
            pass
    return max(0.1, 1.0 + frequency + errors + age)


def _weighted_sample(items: list, count: int, rng: random.Random, weight):
    pool = list(items)
    selected = []
    for _ in range(count):
        if not pool:
            break
        weights = [max(0.1, float(weight(item))) for item in pool]
        target = rng.random() * sum(weights)
        cursor = 0.0
        chosen_index = len(pool) - 1
        for index, current_weight in enumerate(weights):
            cursor += current_weight
            if cursor >= target:
                chosen_index = index
                break
        selected.append(pool.pop(chosen_index))
    return selected


def _group_by_session(candidates: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for candidate in candidates:
        groups[int(candidate["source_session_id"])].append(candidate)
    return [
        {
            "session_id": session_id,
            "questions": sorted(rows, key=lambda row: int(row["source_position"])),
            "weight": max(_candidate_weight(row) for row in rows),
        }
        for session_id, rows in groups.items()
    ]


def _select_groups(candidates: list[dict], count: int, rng: random.Random) -> list[dict]:
    groups = [group for group in _group_by_session(candidates) if len(group["questions"]) >= 2]
    if len(groups) < count:
        raise ValueError(f"Pas assez de dossiers candidats ({len(groups)} disponibles, {count} requis)")
    return _weighted_sample(groups, count, rng, lambda group: group["weight"])


def _select_series(candidates: list[dict], count: int, rng: random.Random, excluded_sessions: set[int] | None = None):
    excluded = excluded_sessions or set()
    groups = [group for group in _group_by_session(candidates) if group["session_id"] not in excluded]
    if len(groups) < count:
        raise ValueError(f"Pas assez de dossiers candidats pour la série ({len(groups)} disponibles, {count} requis)")
    selected_groups = _weighted_sample(groups, count, rng, lambda group: group["weight"])
    return [
        _weighted_sample(group["questions"], 1, rng, _candidate_weight)[0]
        for group in selected_groups
    ]


def _flatten_groups(groups: list[dict]) -> list[dict]:
    return [question for group in groups for question in group["questions"]]


def compose_exam_session(
    *,
    format: ExamFormat,
    seed: str,
    subject: str | None = None,
    dp_count: int = 3,
    question_count: int = 20,
    duration_seconds: int | None = None,
) -> dict:
    """Compose et fige une épreuve, puis crée sa session React."""
    if format not in DEFAULT_DURATIONS:
        raise ValueError(f"Format d'épreuve inconnu: {format}")
    if not str(seed).strip():
        raise ValueError("Le seed de composition est obligatoire")
    if dp_count <= 0 or question_count <= 0:
        raise ValueError("Les quantités de dossiers et questions doivent être positives")

    candidates = local_store.list_uness_exam_candidates(subject=subject)
    if not candidates:
        raise ValueError("Aucun candidat UNESS disponible pour cette composition")
    rng = random.Random(str(seed))

    source_session_ids: list[int] = []
    selected: list[dict]
    if format == "dp":
        groups = _select_groups(candidates, dp_count, rng)
        selected = _flatten_groups(groups)
        source_session_ids = [group["session_id"] for group in groups]
    elif format == "series":
        selected = _select_series(candidates, question_count, rng)
        source_session_ids = [int(row["source_session_id"]) for row in selected]
    else:
        groups = _select_groups(candidates, dp_count, rng)
        source_session_ids = [group["session_id"] for group in groups]
        selected = _flatten_groups(groups)
        isolated = _select_series(
            candidates,
            question_count,
            rng,
            excluded_sessions=set(source_session_ids),
        )
        selected.extend(isolated)
        source_session_ids.extend(int(row["source_session_id"]) for row in isolated)

    question_payloads = [
        {
            "prompt": row["prompt"],
            "choices": row["choices"],
            "answer": row["answer"],
            "explanation": row["explanation"],
            "kind": row["question_kind"],
            "source_refs": row["source_refs"],
            "import_metadata": row["import_metadata"],
            "item_numbers": row["item_numbers"],
        }
        for row in selected
    ]
    practice_kind = PracticeKind.DP if format in {"dp", "mixed"} else PracticeKind.QCM
    item_numbers = tuple(dict.fromkeys(
        item
        for row in selected
        for item in row.get("item_numbers", ())
        if str(item).strip()
    ))
    spec = PracticeSessionSpec(
        practice_kind=practice_kind,
        total_questions=len(question_payloads),
        open_questions=sum(1 for row in selected if not row["choices"]),
        closed_questions=sum(1 for row in selected if row["choices"]),
        item_number=item_numbers[0] if len(item_numbers) == 1 else "",
        item_numbers=item_numbers,
        course_id="exam-blanc",
        course_title=f"Concours blanc {format.upper()} — seed {seed}",
        difficulty=PracticeDifficulty.CONCOURS,
    )
    duration = int(duration_seconds or DEFAULT_DURATIONS[format])
    session_id = local_store.create_ai_practice_session(
        spec=spec,
        questions=question_payloads,
        model="exam-composer-v1",
        exam_mode=True,
        exam_format=format,
        exam_seed=str(seed),
        duration_seconds=duration,
    )
    new_question_ids = [
        int(row["id"])
        for row in local_store.get_ai_practice_session(session_id)
    ]
    local_store.save_exam_composition(
        session_id,
        format=format,
        seed=str(seed),
        duration_seconds=duration,
        question_ids=new_question_ids,
        source_session_ids=source_session_ids,
        subject=str(subject or ""),
    )
    return {
        "session_id": session_id,
        "format": format,
        "seed": str(seed),
        "duration_seconds": duration,
        "question_ids": new_question_ids,
        "source_session_ids": source_session_ids,
    }
