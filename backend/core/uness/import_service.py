"""Local-only import of verified UNESS artifacts into replayable QCM sessions."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.core.practice.models import (
    PracticeDifficulty,
    PracticeKind,
    PracticeSessionSpec,
    QuestionKind,
)
from backend.core.reviews import local_store

from .json_io import load_exam
from .models import UnessExam, UnessProposition, UnessQuestion, _assert_no_sensitive_data


_ROOT = Path(__file__).resolve().parents[3]
IMPORT_DIR = Path(os.environ.get("UNESS_IMPORT_DIR", _ROOT / "data" / "uness" / "imports"))


def load_local_exam(path: str | Path) -> UnessExam:
    """Load an artifact only when it is inside the configured local inbox."""
    root = IMPORT_DIR.resolve()
    requested = Path(path)
    candidate = (root / requested).resolve() if not requested.is_absolute() else requested.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PermissionError("Le fichier UNESS doit être dans le répertoire d'import local") from exc
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    return load_exam(candidate)


def _effective_answer(proposition: UnessProposition) -> bool | None:
    """Use the independent IA verdict when available, otherwise the official answer."""
    return proposition.verdict_ia if proposition.verdict_ia is not None else proposition.reponse_uness


def _choice_answers(question: UnessQuestion, *, official: bool) -> list[str]:
    answers = []
    for proposition in question.propositions:
        answer = proposition.reponse_uness if official else _effective_answer(proposition)
        if answer is True:
            answers.append(proposition.texte)
    return answers


def _primary_explanation(question: UnessQuestion) -> str:
    explanations = [
        f"{proposition.id}. {proposition.explication_ia.strip()}"
        for proposition in question.propositions
        if proposition.explication_ia.strip()
    ]
    if explanations:
        return "\n".join(explanations)
    return "Explication IA non disponible ; consultez la correction officielle."


def _source_refs(question: UnessQuestion, exam: UnessExam) -> list[str]:
    refs = [source for proposition in question.propositions for source in proposition.sources_ia]
    artifact = str(exam.provenance.get("artifact_path", "")).strip()
    if artifact:
        refs.append(f"UNESS: {artifact}")
    return list(dict.fromkeys(ref for ref in refs if ref))


def _question_metadata(question: UnessQuestion, exam: UnessExam) -> dict[str, Any]:
    primary_answer = _choice_answers(question, official=False)
    official_answer = _choice_answers(question, official=True)
    return {
        "uness": {
            "provenance": dict(exam.provenance),
            "exam": {
                "faculty": exam.faculty,
                "level": exam.level,
                "year": exam.year,
                "title": exam.title,
                "dp_context": dict(exam.dp_context),
            },
            "question": {
                "id": question.id,
                "type_question": question.type_question,
                "support_visuel_seul": question.support_visuel_seul,
                "dp_context": dict(question.dp_context),
                "images": [image.to_dict() for image in question.images],
            },
            "propositions": [proposition.to_dict() for proposition in question.propositions],
        },
        "correction": {
            "primary": {
                "source": "ia" if any(p.verdict_ia is not None for p in question.propositions) else "uness",
                "answer": primary_answer,
                "explanation": _primary_explanation(question),
            },
            "official": {
                "source": "UNESS",
                "answer": official_answer,
                "available": any(p.reponse_uness is not None for p in question.propositions),
            },
        },
    }


def _practice_kind(exam: UnessExam) -> PracticeKind:
    types = {question.type_question for question in exam.questions}
    if types == {"DP"}:
        return PracticeKind.DP
    if types == {"KFP"}:
        return PracticeKind.KFP
    return PracticeKind.QCM


def _session_value(exam: UnessExam, name: str) -> str:
    value = exam.metadata.get(name, exam.provenance.get(name, ""))
    return str(value) if value is not None else ""


def _to_practice_question(question: UnessQuestion, exam: UnessExam) -> dict[str, Any]:
    kind = QuestionKind.CLOSED if len(question.propositions) >= 2 else QuestionKind.OPEN
    choices = [proposition.texte for proposition in question.propositions]
    metadata = _question_metadata(question, exam)
    primary = metadata["correction"]["primary"]
    answer = primary["answer"]
    return {
        "kind": kind,
        "prompt": question.enonce,
        "choices": choices,
        "answer": "\n".join(answer) if kind is QuestionKind.OPEN else json.dumps(answer, ensure_ascii=False),
        "explanation": primary["explanation"],
        "source_refs": _source_refs(question, exam),
        "import_metadata": metadata,
    }


def import_uness_exam(exam: UnessExam) -> int:
    """Create one local, replayable practice session from a verified UNESS exam."""
    _assert_no_sensitive_data(exam.to_dict())
    if not exam.questions:
        raise ValueError("L'examen UNESS ne contient aucune question importable")
    questions = [_to_practice_question(question, exam) for question in exam.questions]
    closed = sum(question["kind"] is QuestionKind.CLOSED for question in questions)
    spec = PracticeSessionSpec(
        practice_kind=_practice_kind(exam),
        total_questions=len(questions),
        open_questions=len(questions) - closed,
        closed_questions=closed,
        course_id=_session_value(exam, "course_id"),
        course_title=exam.title,
        item_number=_session_value(exam, "item_number"),
        difficulty=PracticeDifficulty.EDN,
    )
    return local_store.create_ai_practice_session(spec=spec, questions=questions, model="uness-verified-local")


def count_disagreements(exam: UnessExam) -> int:
    """Count proposition-level IA/official disagreements for the import response."""
    return sum(
        proposition.statut == "desaccord"
        for question in exam.questions
        for proposition in question.propositions
    )
