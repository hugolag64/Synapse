"""Import idempotent des corrections EDNpro observées dans Chromium.

Ce module ne pilote pas les réponses et ne cherche pas à contourner le site.
L'agent local lui transmet uniquement des snapshots de questions déjà corrigées.
"""

from __future__ import annotations

import datetime as _datetime
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse

from loguru import logger

from backend.core.reviews import local_store
from backend.core.ednpro.rank_inference import (
    build_rank_inference_prompt,
    group_missing_rank_questions,
    parse_rank_inference_response,
)


def extract_corrected_observation(html: str, *, source_url: str = "") -> EdnproQuestionObservation | None:
    """Extract one corrected question from the currently rendered DOM.

    The selectors intentionally prefer semantic/data attributes and fall back
    to the stable visual concepts (question card, proposition, explanation).
    It never makes a network request and returns None until a correction is
    visible in the page.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:  # pragma: no cover - dependency is part of production requirements
        return None
    soup = BeautifulSoup(html or "", "html.parser")
    containers = soup.select(
        "[data-qcm-question], [data-question-id], article.question, .question-card, [data-question]"
    )
    if not containers:
        containers = [
            candidate
            for candidate in soup.select("div.rounded-lg.border")
            if re.search(r"\bitem\s*#?\s*\d+\b", candidate.get_text(" ", strip=True), re.IGNORECASE)
            and candidate.select("button.w-full.text-left")
        ]
    if not containers:
        return None
    container = containers[0]

    def node_text(selector: str) -> str:
        node = container.select_one(selector)
        return node.get_text(" ", strip=True) if node else ""

    def attr(*names: str) -> str:
        for name in names:
            value = container.get(name)
            if value is not None and _text(value):
                return _text(value)
        return ""

    qid = attr("data-qcm-question", "data-question-id", "data-question", "data-id")
    prompt = node_text(
        "[data-question-stem], [data-stem], .question-stem, .question-text, .stem, h3, h4, p[class*='text-base']"
    )
    choices_nodes = container.select(
        "[data-choice-id], [data-proposition-id], label.choice, .choice, .proposition, button.w-full.text-left"
    )
    choices: list[dict[str, Any]] = []
    for index, choice in enumerate(choices_nodes, start=1):
        choice_id = _text(choice.get("data-choice-id") or choice.get("data-proposition-id") or choice.get("data-id"))
        choice_id = choice_id or f"{qid}-p{index}"
        classes = " ".join(choice.get("class", []))
        label_node = choice.select_one("span[class*='leading-relaxed'][class*='flex-1']")
        text = label_node.get_text(" ", strip=True) if label_node else choice.get_text(" ", strip=True)
        label_match = re.search(r"\b([A-E])\.", choice.get_text(" ", strip=True))
        if label_match:
            choice_id = label_match.group(1)
        selected = str(choice.get("data-selected") or choice.get("aria-checked") or "").lower() in {"true", "1", "yes"}
        checked = choice.select_one("input:checked")
        selected = selected or checked is not None
        checkbox_spans = choice.select("span.h-5.w-5")
        selected = selected or any(span.select_one("svg") is not None for span in checkbox_spans)
        correct_attr = choice.get("data-correct") or choice.get("data-expected")
        correct = None if correct_attr is None else str(correct_attr).lower() in {"true", "1", "yes", "correct", "vrai"}
        if correct is None and ("correct" in classes.lower() or "vrai" in classes.lower()):
            correct = True
        if correct is None and ("incorrect" in classes.lower() or "faux" in classes.lower()):
            correct = False
        if correct is None:
            verdict_node = next(
                (
                    node
                    for node in choice.select("p")
                    if re.match(r"^\s*(vrai|faux)\b", node.get_text(" ", strip=True), re.IGNORECASE)
                ),
                None,
            )
            if verdict_node:
                correct = bool(re.match(r"^\s*vrai\b", verdict_node.get_text(" ", strip=True), re.IGNORECASE))
        choices.append({"id": choice_id, "text": text, "selected": selected, "correct": correct})

    full_text = container.get_text(" ", strip=True)
    corrected_marker = attr("data-corrected", "data-correction-displayed", "data-answered")
    correction_visible = str(corrected_marker).lower() in {"true", "1", "yes"}
    correction_visible = correction_visible or bool(container.select_one(
        "[data-explanation-simple], [data-explanation-detailed], .explanation-simple, .explanation-detailed, .correction"
    ))
    correction_visible = correction_visible or any(choice.get("correct") is not None for choice in choices)
    correction_visible = correction_visible or bool(
        container.select_one("div[class*='space-y-2']")
        and "explication détaillée" in container.get_text(" ", strip=True).casefold()
    )
    if not correction_visible:
        return None
    rank_match = re.search(r"\brang\s*([ABC])\b", full_text, re.IGNORECASE)
    item_match = re.search(r"\bitem\s*#?\s*([0-9]+)\b", full_text, re.IGNORECASE)
    score_match = re.search(
        r"(?:note\s+(?:obtenue|partielle)?\s*)?([0-9]+(?:[.,][0-9]+)?)\s*/\s*([0-9]+(?:[.,][0-9]+)?)\s*pt",
        full_text,
        re.IGNORECASE,
    )
    if score_match:
        numerator = float(score_match.group(1).replace(",", "."))
        denominator = float(score_match.group(2).replace(",", "."))
        score = round(numerator / denominator * 100, 2) if denominator else None
    else:
        percentage_match = re.search(r"(?:score|note)\s*[: ]\s*([0-9]+(?:[.,][0-9]+)?)\s*%", full_text, re.IGNORECASE)
        score = float(percentage_match.group(1).replace(",", ".")) if percentage_match else None
    simple_parts = []
    for choice in choices:
        choice_node = next(
            (
                node
                for node in choices_nodes
                if _text(node.get("data-choice-id") or node.get("data-proposition-id") or "") == choice["id"]
                or re.search(rf"\b{re.escape(choice['id'])}\.", node.get_text(" ", strip=True))
            ),
            None,
        )
        explanation = choice_node.select_one(".prose") if choice_node else None
        if explanation:
            simple_parts.append(f"{choice['id']}. {explanation.get_text(' ', strip=True)}")
    detail_node = next(
        (
            node
            for node in container.select("div")
            if node.get_text(" ", strip=True).casefold().startswith("explication détaillée par ia")
        ),
        None,
    )
    detail_text = detail_node.get_text(" ", strip=True) if detail_node else ""
    correct_answers_match = re.search(
        r"réponses?\s+correctes?\s+(?:sont|:)\s+([^\.\n]+)",
        detail_text,
        re.IGNORECASE,
    )
    if correct_answers_match:
        correct_answers = tuple(dict.fromkeys(
            re.findall(r"\b([A-E])\b", correct_answers_match.group(1).upper())
        ))
        for choice in choices:
            choice["correct"] = choice["id"] in correct_answers
    else:
        correct_answers = tuple(choice["id"] for choice in choices if choice.get("correct") is True)
    selected_answers = tuple(choice["id"] for choice in choices if choice.get("selected"))
    question_match = re.search(r"question\s+(\d+)\s*/\s*(\d+)", soup.get_text(" ", strip=True), re.IGNORECASE)
    external_id = qid
    if not external_id and question_match:
        position = int(question_match.group(1)) - 1
        query = parse_qs(urlparse(source_url).query)
        external_ids = [
            *query.get("legacyQids", [""])[0].split(","),
            *query.get("iqIds", [""])[0].split(","),
        ]
        if 0 <= position < len(external_ids):
            external_id = _text(external_ids[position])
    if not external_id:
        external_id = f"dom-{hashlib.sha1(prompt.encode('utf-8')).hexdigest()[:16]}"
    return EdnproQuestionObservation(
        external_question_id=external_id,
        item_number=attr("data-item-number", "data-item") or (item_match.group(1) if item_match else ""),
        prompt=prompt or full_text,
        choices=tuple(choices),
        correct_answers=correct_answers,
        selected_answers=selected_answers,
        explanation_simple="\n".join(simple_parts),
        explanation_detailed=detail_text or node_text(
            "[data-explanation-detailed], .explanation-detailed, .ai-explanation, .correction"
        ),
        rank=rank_match.group(1).upper() if rank_match else "",
        rank_source="ednpro" if rank_match else "unknown",
        rank_confidence=1.0 if rank_match else None,
        question_type=attr("data-question-type", "data-type") or "QCM",
        score_percent=score,
        is_correct=(score >= 100.0) if score is not None else (
            set(selected_answers) == set(correct_answers) if correct_answers else None
        ),
        corrected=True,
        source_url=source_url,
    )


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _should_replace_rank(
    existing_rank: str,
    existing_source: str,
    incoming_rank: str,
    incoming_source: str,
) -> bool:
    """Keep official EDNpro metadata ahead of inferred metadata."""
    if incoming_rank not in {"A", "B"}:
        return False
    if existing_rank not in {"A", "B"}:
        return True
    priority = {"unknown": 0, "gemini": 1, "oic": 2, "ednpro": 3}
    return priority.get(incoming_source, 0) > priority.get(existing_source, 0)


def _tuple_text(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (_text(value),) if _text(value) else ()
    return tuple(value for value in (_text(entry) for entry in value) if value)


def _first(mapping: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return default


@dataclass(frozen=True)
class EdnproQuestionObservation:
    """Une question dont la correction a été affichée à l'utilisateur."""

    external_question_id: str
    item_number: str
    prompt: str
    choices: tuple[dict[str, Any], ...] = ()
    correct_answers: tuple[str, ...] = ()
    selected_answers: tuple[str, ...] = ()
    explanation_simple: str = ""
    explanation_detailed: str = ""
    rank: str = ""
    rank_source: str = "unknown"
    rank_confidence: float | None = None
    rank_evidence: tuple[str, ...] = ()
    question_type: str = "QCM"
    score_percent: float | None = None
    is_correct: bool | None = None
    corrected: bool = False
    source_url: str = ""
    observed_at: str = ""


@dataclass(frozen=True)
class EdnproImportResult:
    session_id: int
    imported_questions: int
    discarded_questions: int
    new_questions: int
    new_attempts: int
    duplicate_attempts: int
    item_stats: dict[str, dict[str, Any]] = field(default_factory=dict)
    session_item_stats: dict[str, dict[str, Any]] = field(default_factory=dict)


def normalize_observation(raw: Mapping[str, Any] | EdnproQuestionObservation) -> EdnproQuestionObservation:
    """Normalise un snapshot DOM/API en contrat stable pour l'import.

    Les clés acceptées couvrent à la fois le payload de l'agent et les noms
    courants affichés par la page de correction. La fonction reste pure pour
    être testée sur des fixtures sans Chromium.
    """
    if isinstance(raw, EdnproQuestionObservation):
        return raw
    question = raw.get("question") if isinstance(raw.get("question"), Mapping) else raw
    correction = raw.get("correction") if isinstance(raw.get("correction"), Mapping) else raw
    choices = _first(question, "choices", "propositions", default=()) or ()
    normalized_choices = tuple(dict(choice) for choice in choices if isinstance(choice, Mapping))
    selected = _tuple_text(_first(correction, "selected_answers", "selected", "response", default=()))
    correct = _tuple_text(_first(correction, "correct_answers", "expected", "answer", default=()))
    if not selected:
        selected = tuple(_text(choice.get("id") or choice.get("key") or choice.get("label"))
                         for choice in normalized_choices if choice.get("selected"))
        selected = tuple(value for value in selected if value)
    if not correct:
        correct = tuple(_text(choice.get("id") or choice.get("key") or choice.get("label"))
                        for choice in normalized_choices if choice.get("correct") or choice.get("expected"))
        correct = tuple(value for value in correct if value)

    score_raw = _first(correction, "score_percent", "score", "percentage")
    try:
        score = float(score_raw) if score_raw is not None and _text(score_raw) else None
    except (TypeError, ValueError):
        score = None
    displayed = _first(correction, "displayed", "corrected", "correction_displayed", default=False)
    corrected = bool(displayed) or score is not None or _first(correction, "is_correct") is not None
    is_correct_raw = _first(correction, "is_correct", "correct")
    is_correct = None if is_correct_raw is None else bool(is_correct_raw)
    if is_correct is None and score is not None:
        is_correct = score >= 100.0

    rank = _text(_first(question, "rank", "rang", "level")).upper()
    rank_source = _text(_first(question, "rank_source", "rankSource", default=""))
    if not rank_source:
        rank_source = "ednpro" if rank in {"A", "B"} else "unknown"
    rank_confidence_raw = _first(question, "rank_confidence", "rankConfidence")
    try:
        rank_confidence = float(rank_confidence_raw) if rank_confidence_raw is not None else (
            1.0 if rank_source == "ednpro" and rank in {"A", "B"} else None
        )
    except (TypeError, ValueError):
        rank_confidence = None
    rank_evidence = _tuple_text(_first(question, "rank_evidence", "rankEvidence", default=()))

    return EdnproQuestionObservation(
        external_question_id=_text(_first(question, "external_question_id", "id", "question_id", "qid")),
        item_number=_text(_first(question, "item_number", "item", "itemNumber")),
        prompt=_text(_first(question, "prompt", "question", "title", default="")),
        choices=normalized_choices,
        correct_answers=correct,
        selected_answers=selected,
        explanation_simple=_text(_first(question, "explanation_simple", "simple_explanation", "explanation")),
        explanation_detailed=_text(_first(question, "explanation_detailed", "detailed_explanation", "ai_explanation")),
        rank=rank,
        rank_source=rank_source,
        rank_confidence=rank_confidence,
        rank_evidence=rank_evidence,
        question_type=_text(_first(question, "question_type", "type", "kind", default="QCM")).upper(),
        score_percent=score,
        is_correct=is_correct,
        corrected=corrected,
        source_url=_text(_first(raw, "source_url", "url")),
        observed_at=_text(_first(raw, "observed_at", "timestamp")),
    )


def _course_item_number(course: Any) -> str:
    return _text(
        getattr(course, "item_number", "")
        or getattr(course, "display_item_number", "")
        or (course.get("item_number", "") if isinstance(course, Mapping) else "")
    )


def _observation_id(observation: EdnproQuestionObservation) -> str:
    return _text(observation.external_question_id)


def enrich_session_ranks(
    session: Mapping[str, Any],
    *,
    courses: Any = (),
    service: Any = None,
) -> dict[str, Any]:
    """Infer missing ranks in one Gemini request per item, best effort."""
    raw_questions = tuple(session.get("questions") or ())
    observations = tuple(normalize_observation(row) for row in raw_questions)
    groups = group_missing_rank_questions(observations)
    if not groups:
        return dict(session)

    from backend.core.ai.tasks import infer_ednpro_ranks

    if service is None:
        from backend.config.settings import settings

        if not settings.gemini_api_key:
            return dict(session)

    course_ids_by_item: dict[str, list[str]] = {}
    for course in courses or ():
        item_number = _course_item_number(course)
        course_id = _text(
            getattr(course, "id", "")
            or (course.get("id", "") if isinstance(course, Mapping) else "")
        )
        if item_number and course_id:
            course_ids_by_item.setdefault(item_number, []).append(course_id)

    replacements: dict[str, EdnproQuestionObservation] = {}
    for item_number, item_questions in groups.items():
        try:
            oics = local_store.get_lisa_oic_for_item(
                item_number,
                course_ids_by_item.get(item_number, []),
            )
            if not oics:
                continue
            prompt = build_rank_inference_prompt(item_number, item_questions, oics)
            response = infer_ednpro_ranks(prompt, service=service)
            inferred = parse_rank_inference_response(
                response.text,
                [_observation_id(row) for row in item_questions],
            )
        except Exception as exc:
            logger.warning("Inférence de rang EDNpro ignorée pour l'item {} : {}", item_number, exc)
            continue
        by_id = {_observation_id(row): row for row in item_questions}
        for question_id, result in inferred.items():
            original = by_id.get(question_id)
            if original is None:
                continue
            replacements[question_id] = replace(
                original,
                rank=result.rank,
                rank_source=result.source,
                rank_confidence=result.confidence,
                rank_evidence=result.oic_codes,
            )

    enriched = [replacements.get(_observation_id(observation), observation) for observation in observations]
    result = dict(session)
    result["questions"] = [asdict(observation) for observation in enriched]
    return result


def _session_date(raw: Any) -> str:
    value = _text(raw)
    return value or _datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def import_session(session: Mapping[str, Any]) -> EdnproImportResult:
    """Importe une session corrigée de façon transactionnelle et idempotente."""
    observations = tuple(normalize_observation(row) for row in (session.get("questions") or ()))
    corrected = tuple(row for row in observations if row.corrected and row.external_question_id)
    discarded = len(observations) - len(corrected)
    external_session_id = _text(session.get("external_session_id") or session.get("session_id"))
    if not external_session_id:
        raise ValueError("external_session_id est requis pour importer une session EDNpro")
    now = _datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    metadata = {key: value for key, value in session.items() if key not in {"questions"}}

    new_questions = new_attempts = duplicate_attempts = 0
    with local_store._conn() as con:
        con.execute(
            """INSERT INTO ednpro_qcm_sessions
               (external_session_id, session_date, score_percent, total_questions,
                correct_answers, wrong_answers, imported_questions, raw_metadata_json,
                created_at, imported_at)
               VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
               ON CONFLICT(external_session_id) DO UPDATE SET
                 score_percent=excluded.score_percent,
                 total_questions=excluded.total_questions,
                 correct_answers=excluded.correct_answers,
                 wrong_answers=excluded.wrong_answers,
                 raw_metadata_json=excluded.raw_metadata_json,
                 imported_at=excluded.imported_at""",
            (
                external_session_id,
                _session_date(session.get("session_date")),
                session.get("score_percent"),
                session.get("total_questions") or len(observations),
                session.get("correct_answers"),
                session.get("wrong_answers"),
                json.dumps(metadata, ensure_ascii=False, sort_keys=True, default=str),
                now,
                now,
            ),
        )
        session_row = con.execute(
            "SELECT id FROM ednpro_qcm_sessions WHERE external_session_id = ?", (external_session_id,)
        ).fetchone()
        assert session_row is not None
        persisted_session_id = int(session_row["id"])

        for observation in corrected:
            con.execute(
                """INSERT INTO ednpro_qcm_questions
                   (external_question_id, item_number, prompt, question_type,
                    choices_json, correct_answers_json, explanation_simple,
                    explanation_detailed, rank, rank_source, rank_confidence,
                    rank_evidence_json, source_url, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(external_question_id) DO NOTHING""",
                (
                    observation.external_question_id,
                    observation.item_number,
                    observation.prompt,
                    observation.question_type,
                    json.dumps(observation.choices, ensure_ascii=False, sort_keys=True),
                    json.dumps(observation.correct_answers, ensure_ascii=False),
                    observation.explanation_simple,
                    observation.explanation_detailed,
                    observation.rank,
                    observation.rank_source,
                    observation.rank_confidence,
                    json.dumps(observation.rank_evidence, ensure_ascii=False),
                    observation.source_url,
                    now,
                    now,
                ),
            )
            inserted_question = int(con.execute("SELECT changes()").fetchone()[0] == 1)
            new_questions += inserted_question
            if not inserted_question and observation.rank in {"A", "B"}:
                existing_question = con.execute(
                    "SELECT rank, rank_source FROM ednpro_qcm_questions "
                    "WHERE external_question_id = ?",
                    (observation.external_question_id,),
                ).fetchone()
                if existing_question is not None and _should_replace_rank(
                    str(existing_question["rank"] or ""),
                    str(existing_question["rank_source"] or "unknown"),
                    observation.rank,
                    observation.rank_source,
                ):
                    con.execute(
                        """UPDATE ednpro_qcm_questions
                           SET rank = ?, rank_source = ?, rank_confidence = ?,
                               rank_evidence_json = ?, updated_at = ?
                           WHERE external_question_id = ?""",
                        (
                            observation.rank,
                            observation.rank_source,
                            observation.rank_confidence,
                            json.dumps(observation.rank_evidence, ensure_ascii=False),
                            now,
                            observation.external_question_id,
                        ),
                    )
            question_row = con.execute(
                "SELECT id FROM ednpro_qcm_questions WHERE external_question_id = ?",
                (observation.external_question_id,),
            ).fetchone()
            assert question_row is not None
            question_id = int(question_row["id"])
            con.execute(
                """INSERT INTO ednpro_qcm_attempts
                   (session_id, question_id, selected_answers_json, is_correct,
                    score_percent, rank, rank_source, rank_confidence,
                    rank_evidence_json, response_json, answered_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(session_id, question_id) DO NOTHING""",
                (
                    persisted_session_id,
                    question_id,
                    json.dumps(observation.selected_answers, ensure_ascii=False),
                    None if observation.is_correct is None else int(observation.is_correct),
                    observation.score_percent,
                    observation.rank,
                    observation.rank_source,
                    observation.rank_confidence,
                    json.dumps(observation.rank_evidence, ensure_ascii=False),
                    json.dumps({"selected_answers": observation.selected_answers}, ensure_ascii=False),
                    observation.observed_at or now,
                ),
            )
            inserted_attempt = int(con.execute("SELECT changes()").fetchone()[0] == 1)
            new_attempts += inserted_attempt
            duplicate_attempts += 1 - inserted_attempt

        imported_total = con.execute(
            "SELECT COUNT(*) FROM ednpro_qcm_attempts WHERE session_id = ?",
            (persisted_session_id,),
        ).fetchone()[0]
        con.execute(
            "UPDATE ednpro_qcm_sessions SET imported_questions = ? WHERE id = ?",
            (imported_total, persisted_session_id),
        )

    session_item_stats = _stats_for_observations(corrected)
    return EdnproImportResult(
        session_id=persisted_session_id,
        imported_questions=new_attempts,
        discarded_questions=discarded,
        new_questions=new_questions,
        new_attempts=new_attempts,
        duplicate_attempts=duplicate_attempts,
        item_stats={row: get_item_stats(row) for row in {q.item_number for q in corrected if q.item_number}},
        session_item_stats=session_item_stats,
    )


def _stats_for_observations(observations: tuple[EdnproQuestionObservation, ...]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item_number in sorted({row.item_number for row in observations if row.item_number}):
        rows = [row for row in observations if row.item_number == item_number]
        scores = [row.score_percent for row in rows if row.score_percent is not None]
        result[item_number] = {
            "attempts": len(rows),
            "correct": sum(row.is_correct is True for row in rows),
            "wrong": sum(row.is_correct is False for row in rows),
            "average_score_percent": round(sum(scores) / len(scores), 2) if scores else None,
            "rank_a": {
                "attempts": sum(row.rank == "A" for row in rows),
                "correct": sum(row.rank == "A" and row.is_correct is True for row in rows),
                "wrong": sum(row.rank == "A" and row.is_correct is False for row in rows),
            },
            "rank_b": {
                "attempts": sum(row.rank == "B" for row in rows),
                "correct": sum(row.rank == "B" and row.is_correct is True for row in rows),
                "wrong": sum(row.rank == "B" and row.is_correct is False for row in rows),
            },
        }
    return result


def record_imported_evaluations(
    *,
    session: Mapping[str, Any],
    result: EdnproImportResult,
    course_resolver,
) -> list[int]:
    """Publie une évaluation QCM par item dans le moteur de maîtrise.

    course_resolver retourne un objet/dict avec id et éventuellement title.
    L'absence de cours local ne bloque jamais l'import du contenu.
    """
    if not result.new_attempts:
        return []
    from backend.core.evaluation.models import EvaluationInput
    from backend.core.evaluation.service import record_evaluation

    session_date = _session_date(session.get("session_date")).split("T", 1)[0]
    persisted_ids: list[int] = []
    for item_number, stats in result.session_item_stats.items():
        course = course_resolver(item_number)
        if course is None:
            continue
        if isinstance(course, Mapping):
            course_id = _text(course.get("id"))
            course_title = _text(course.get("title") or course.get("name"))
        else:
            course_id = _text(getattr(course, "id", ""))
            course_title = _text(getattr(course, "title", ""))
        if not course_id:
            continue
        outcome = record_evaluation(EvaluationInput(
            source="qcm",
            course_id=course_id,
            item_number=item_number,
            course_title=course_title,
            score_percent=stats["average_score_percent"],
            total_questions=stats["attempts"],
            correct_answers=stats["correct"],
            wrong_answers=stats["wrong"],
            session_type="QCM",
            platform="EDNpro",
            session_date=session_date,
        ))
        persisted_ids.append(outcome.persisted_id)
    return persisted_ids


def get_item_stats(item_number: str) -> dict[str, Any]:
    """Retourne les statistiques importées, ventilées par rang A/B."""
    with local_store._conn() as con:
        rows = con.execute(
            """SELECT a.is_correct, a.score_percent, a.rank
               FROM ednpro_qcm_attempts a
               JOIN ednpro_qcm_questions q ON q.id = a.question_id
               WHERE q.item_number = ?
               ORDER BY a.id""",
            (_text(item_number),),
        ).fetchall()

    def bucket(values) -> dict[str, int]:
        return {
            "attempts": len(values),
            "correct": sum(row["is_correct"] == 1 for row in values),
            "wrong": sum(row["is_correct"] == 0 for row in values),
        }

    valid_scores = [float(row["score_percent"]) for row in rows if row["score_percent"] is not None]
    return {
        "attempts": len(rows),
        "correct": sum(row["is_correct"] == 1 for row in rows),
        "wrong": sum(row["is_correct"] == 0 for row in rows),
        "average_score_percent": round(sum(valid_scores) / len(valid_scores), 2) if valid_scores else None,
        "rank_a": bucket([row for row in rows if str(row["rank"] or "").upper() == "A"]),
        "rank_b": bucket([row for row in rows if str(row["rank"] or "").upper() == "B"]),
    }
