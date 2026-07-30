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
UNESS_ROOT = Path(os.environ.get("UNESS_ROOT", _ROOT / "UNESS"))
TO_REVIEW_DIR = Path(os.environ.get("UNESS_TO_REVIEW_DIR", UNESS_ROOT / "à_vérifier"))
VERIFIED_DIR = Path(os.environ.get("UNESS_VERIFIED_DIR", UNESS_ROOT / "vérifiés"))
ARCHIVE_DIR = Path(os.environ.get("UNESS_ARCHIVE_DIR", UNESS_ROOT / "archives"))
ARTIFACT_DIR = Path(
    os.environ.get("UNESS_ARTIFACT_DIR", _ROOT / "data" / "uness" / "artifacts")
)

ANNALE_TYPE_LABELS = {
    "matiere": "Matière",
    "concours_blanc": "Concours blanc",
    "vrai_concours": "Vrai concours",
    "edn_complet": "EDN complet",
}


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
    try:
        return load_exam(candidate)
    except (AttributeError, TypeError) as exc:
        raise ValueError("Artéfact UNESS invalide : structure JSON attendue") from exc


def scan_verified_exams() -> list[Path]:
    """List JSON outputs manually returned by ChatGPT, excluding the index."""
    VERIFIED_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(path for path in VERIFIED_DIR.glob("*.json") if path.name != ".imported.json")


def _exam_fingerprint(exam: UnessExam) -> str:
    import hashlib
    raw = f"{exam.faculty}|{exam.level}|{exam.year}|{exam.title}|" + "|".join(q.id for q in exam.questions)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _annale_group_title(exam: UnessExam) -> str:
    """Recover the shared course title from convert_chatgpt_export.py's '{course} — {part}' convention."""
    return exam.title.rsplit(" — ", 1)[0] if " — " in exam.title else exam.title


def _group_files_by_source_url(paths: list[Path]) -> dict[str, list[tuple[Path, UnessExam]]]:
    groups: dict[str, list[tuple[Path, UnessExam]]] = {}
    for path in paths:
        exam = load_exam(path)
        source_url = str(exam.provenance.get("source_url", "")).strip()
        groups.setdefault(source_url, []).append((path, exam))
    return groups


def import_verified_directory(tags: dict[str, str] | None = None) -> dict[str, Any]:
    """Validate and import all new verified outputs, grouped by partiel, without aborting the batch."""
    tags = tags or {}
    index_path = VERIFIED_DIR / ".imported.json"
    try:
        imported = set(json.loads(index_path.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError, TypeError):
        imported = set()
    result: dict[str, Any] = {"imported": [], "skipped": [], "errors": [], "pending_tag": []}

    for source_url, entries in _group_files_by_source_url(scan_verified_exams()).items():
        annale = local_store.get_uness_annale_by_source_url(source_url) if source_url else None
        if annale is None and source_url:
            type_annale = tags.get(source_url)
            if type_annale is None:
                first_path, first_exam = entries[0]
                result["pending_tag"].append(
                    {
                        "source_url": source_url,
                        "faculte": first_exam.faculty,
                        "niveau": first_exam.level,
                        "annee": first_exam.year,
                        "matiere": str(first_exam.metadata.get("subject", "")),
                        "titre": _annale_group_title(first_exam),
                        "files": [path.name for path, _ in entries],
                    }
                )
                continue
            _, first_exam = entries[0]
            annale_id = local_store.create_uness_annale(
                source_url=source_url,
                collected_at=str(first_exam.provenance.get("collected_at", "")).strip(),
                faculte=first_exam.faculty,
                niveau=first_exam.level,
                annee=first_exam.year,
                matiere=str(first_exam.metadata.get("subject", "")),
                titre=_annale_group_title(first_exam),
                type_annale=type_annale,
            )
            annale = local_store.get_uness_annale(annale_id)

        for path, exam in entries:
            try:
                fingerprint = _exam_fingerprint(exam)
                if fingerprint in imported:
                    result["skipped"].append(path.name)
                    continue
                session_id = import_uness_exam(exam)
                if annale is not None:
                    local_store.set_session_annale_id(session_id, annale["id"])
                imported.add(fingerprint)
                result["imported"].append(
                    {"file": path.name, "session_id": session_id, "disagreements": count_disagreements(exam)}
                )
                ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
                path.replace(ARCHIVE_DIR / path.name)
                collected_at = str(exam.provenance.get("collected_at", "")).strip()
                for candidate in TO_REVIEW_DIR.glob("*.json"):
                    try:
                        source = json.loads(candidate.read_text(encoding="utf-8")).get("source", {})
                    except (OSError, json.JSONDecodeError, AttributeError):
                        continue
                    if collected_at and source.get("collected_at") == collected_at:
                        candidate.replace(ARCHIVE_DIR / f"a_verifier-{candidate.name}")
            except (ValueError, OSError, PermissionError) as exc:
                result["errors"].append({"file": path.name, "error": str(exc)})

    index_path.write_text(json.dumps(sorted(imported), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def resolve_local_media_path(path: str | Path) -> Path:
    """Resolve imported media under configured roots, including workspace-relative defaults."""
    requested = Path(path)
    roots = (IMPORT_DIR.resolve(), ARTIFACT_DIR.resolve())
    candidates = (
        [requested.resolve()]
        if requested.is_absolute()
        else [
            (_ROOT / requested).resolve(),
            (IMPORT_DIR / requested).resolve(),
            (ARTIFACT_DIR / requested).resolve(),
        ]
    )
    allowed_candidates = [
        candidate
        for candidate in dict.fromkeys(candidates)
        if any(candidate == root or candidate.is_relative_to(root) for root in roots)
    ]
    if not allowed_candidates:
        raise PermissionError(path)
    for candidate in allowed_candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(path)


def _effective_answer(proposition: UnessProposition) -> bool | None:
    """Use a manual final answer first, then IA, then the official answer."""
    if proposition.reponse_finale is not None:
        return proposition.reponse_finale
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
    disagreement_comments = [
        proposition.commentaire_desaccord
        for proposition in question.propositions
        if proposition.statut == "desaccord" and proposition.commentaire_desaccord
    ]
    if any(proposition.reponse_finale is not None for proposition in question.propositions):
        primary_source = "validated"
    elif any(proposition.verdict_ia is not None for proposition in question.propositions):
        primary_source = "ia"
    else:
        primary_source = "uness"
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
                "verification_status": question.verification_status,
                "dp_context": dict(question.dp_context),
                "images": [image.to_dict() for image in question.images],
            },
            "propositions": [proposition.to_dict() for proposition in question.propositions],
        },
        "correction": {
            "primary": {
                "source": primary_source,
                "answer": primary_answer,
                "explanation": _primary_explanation(question),
            },
            "official": {
                "source": "UNESS",
                "answer": official_answer,
                "available": bool(question.propositions) and all(
                    proposition.reponse_uness is not None for proposition in question.propositions
                ),
            },
            "disagreement": {
                "present": any(
                    proposition.statut == "desaccord"
                    for proposition in question.propositions
                ),
                "comments": list(dict.fromkeys(disagreement_comments)),
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


def assert_verified_exam(exam: UnessExam) -> None:
    """Reject artifacts that have not completed a coherent proposition-level IA review."""
    for question in exam.questions:
        if question.verification_status == "unsupported":
            raise ValueError(
                f"Échec de vérification IA pour la question {question.id} : "
                "vérification visuelle non prise en charge"
            )
        if question.verification_status == "verified":
            for index, image in enumerate(question.images, start=1):
                if image.metadata.get("verification_status") != "provided_to_ai":
                    raise ValueError(
                        f"Échec de vérification IA pour la question {question.id} : "
                        f"image {index} sans verification_status 'provided_to_ai'"
                    )
        for proposition in question.propositions:
            error_prefix = (
                f"Échec de vérification IA pour la question {question.id}, "
                f"proposition {proposition.id}"
            )
            if proposition.verdict_ia is None:
                raise ValueError(f"{error_prefix} : verdict_ia manquant")
            if not proposition.explication_ia.strip():
                raise ValueError(f"{error_prefix} : explication_ia manquante")
            confidence = proposition.confiance_ia
            if (
                confidence is None
                or isinstance(confidence, bool)
                or not 0.0 <= float(confidence) <= 1.0
            ):
                raise ValueError(f"{error_prefix} : confiance_ia invalide")

            if proposition.reponse_finale is not None:
                expected_status = "valide_manuellement"
            elif proposition.reponse_uness is None:
                expected_status = "incertain"
            elif proposition.reponse_uness == proposition.verdict_ia:
                expected_status = "concordant"
            else:
                expected_status = "desaccord"
            if proposition.statut != expected_status:
                raise ValueError(
                    f"{error_prefix} : statut {proposition.statut!r} incohérent "
                    f"(attendu {expected_status!r})"
                )
            if expected_status == "desaccord" and not proposition.commentaire_desaccord.strip():
                raise ValueError(f"{error_prefix} : commentaire_desaccord manquant")
        if question.verification_status != "verified":
            raise ValueError(
                f"Échec de vérification IA pour la question {question.id} : "
                "verification_status non vérifié"
            )


def import_uness_exam(exam: UnessExam) -> int:
    """Create one local, replayable practice session from a verified UNESS exam."""
    _assert_no_sensitive_data(exam.to_dict())
    assert_verified_exam(exam)
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
