"""Construction du prompt Batch et validation du contrat de réponse pour
l'analyse audio-informée d'un dossier UNESS post-conférence."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from loguru import logger

from backend.core.ai.batch_client import UploadedFile
from backend.core.practice.rank_service import INFERENCE_THRESHOLD

PROMPT_VERSION = "conference-analysis-v1"
_VALID_VERDICTS = {"concordant", "desaccord", "incertain"}


@dataclass(frozen=True)
class ConferenceQuestionSnapshot:
    question_id: str
    enonce: str
    official_answer: str
    official_item: str
    official_rank: str


@dataclass(frozen=True)
class ConferenceQuestionResult:
    item_number: str = ""
    item_confidence: float = 0.0
    item_rationale: str = ""
    item_needs_admin: bool = False
    rank: str = ""
    rank_confidence: float = 0.0
    rank_rationale: str = ""
    rank_needs_admin: bool = False
    verdict: str = "incertain"
    verdict_confidence: float = 0.0
    verdict_rationale: str = ""
    transcript_excerpt: str = ""


@dataclass(frozen=True)
class ConferenceAnalysisResult:
    summary: str = ""
    questions: dict[str, ConferenceQuestionResult] = field(default_factory=dict)


_INSTRUCTIONS = """Tu analyses l'enregistrement audio d'une conférence de médecine et le
dossier UNESS travaillé le même jour. Pour chaque question listée ci-dessous, réponds en
te basant sur ce que dit le professeur dans l'audio :
- item_numbers : uniquement des numéros pris dans la liste "items candidats" fournie pour
  la question ; jamais un numéro hors de cette liste ; laisse vide si absent officiellement
  ET non identifiable avec certitude.
- rank : "A", "B" ou vide si non identifiable.
- verdict : "concordant" si l'audio confirme la correction officielle, "desaccord" si
  l'audio la contredit, "incertain" sinon.
Ne modifie jamais un item ou un rang déjà marqué "officiel" ci-dessous — propose seulement
pour les champs marqués manquants. Réponds en JSON strict :
{"summary": "...", "questions": [{"question_id": "...", "item_numbers": [...],
"item_confidence": 0-1, "item_rationale": "...", "rank": "A|B|", "rank_confidence": 0-1,
"rank_rationale": "...", "verdict": "concordant|desaccord|incertain", "verdict_confidence": 0-1,
"verdict_rationale": "...", "transcript_excerpt": "..."}]}"""


def build_conference_analysis_request(
    *, audio_file: UploadedFile, college_label: str, questions: list[ConferenceQuestionSnapshot],
) -> dict:
    lines = [_INSTRUCTIONS, f"\nCollège : {college_label}\n"]
    for question in questions:
        lines.append(
            f"- question_id={question.question_id} | énoncé: {question.enonce} | "
            f"réponse officielle: {question.official_answer or '(absente)'} | "
            f"item officiel: {question.official_item or '(absent)'} | "
            f"rang officiel: {question.official_rank or '(absent)'}"
        )
    text_prompt = "\n".join(lines)

    parts = [
        {"file_data": {"mime_type": audio_file.mime_type, "file_uri": audio_file.uri}},
        {"text": text_prompt},
    ]
    return {
        "batch": {
            "display_name": f"conference-analysis-{college_label}",
            "input_config": {
                "requests": {
                    "requests": [
                        {
                            "request": {
                                "contents": [{"parts": parts}],
                                "generation_config": {"responseMimeType": "application/json"},
                            },
                            "metadata": {"key": "conference-analysis"},
                        }
                    ]
                }
            },
        }
    }


def parse_conference_analysis_response(
    raw_text: str, *, known_question_ids: set[str], candidate_items: dict[str, set[str]],
) -> ConferenceAnalysisResult:
    try:
        payload = json.loads(raw_text)
    except (TypeError, json.JSONDecodeError) as exc:
        logger.warning(f"Réponse d'analyse conférence invalide (JSON) : {exc}")
        return ConferenceAnalysisResult()

    summary = str(payload.get("summary") or "").strip()
    results: dict[str, ConferenceQuestionResult] = {}

    for entry in payload.get("questions") or []:
        question_id = str(entry.get("question_id") or "").strip()
        if question_id not in known_question_ids:
            continue

        allowed_items = candidate_items.get(question_id, set())
        proposed_items = [str(n).strip() for n in (entry.get("item_numbers") or [])]
        kept_item = next((n for n in proposed_items if n in allowed_items), "")
        item_needs_admin = bool(proposed_items) and not kept_item

        rank = str(entry.get("rank") or "").strip().upper()
        rank_confidence = float(entry.get("rank_confidence") or 0.0)
        rank_needs_admin = rank in {"A", "B"} and rank_confidence < INFERENCE_THRESHOLD
        if rank not in {"A", "B"}:
            rank = ""

        verdict = str(entry.get("verdict") or "incertain").strip().lower()
        if verdict not in _VALID_VERDICTS:
            verdict = "incertain"

        results[question_id] = ConferenceQuestionResult(
            item_number=kept_item,
            item_confidence=float(entry.get("item_confidence") or 0.0),
            item_rationale=str(entry.get("item_rationale") or "").strip(),
            item_needs_admin=item_needs_admin,
            rank=rank,
            rank_confidence=rank_confidence,
            rank_rationale=str(entry.get("rank_rationale") or "").strip(),
            rank_needs_admin=rank_needs_admin,
            verdict=verdict,
            verdict_confidence=float(entry.get("verdict_confidence") or 0.0),
            verdict_rationale=str(entry.get("verdict_rationale") or "").strip(),
            transcript_excerpt=str(entry.get("transcript_excerpt") or "").strip(),
        )

    return ConferenceAnalysisResult(summary=summary, questions=results)
