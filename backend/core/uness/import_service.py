"""Local-only import of verified UNESS artifacts into replayable QCM sessions."""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import Any

from loguru import logger

from backend.core.practice.models import (
    PracticeDifficulty,
    PracticeKind,
    PracticeSessionSpec,
    QuestionKind,
)
from backend.core.reviews import local_store

from .gemini_conversion import convert_raw_payload, is_raw_ai_response
from .json_io import load_exam
from .models import (
    UNSUPPORTED_VISUAL_EXPLANATION,
    UnessExam,
    UnessProposition,
    UnessQuestion,
    _assert_no_sensitive_data,
)

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
    "edn_complet": "EDN complet",
}


def _slug(value: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "content"

# Facultés de médecine françaises (UFR Santé), pour corriger manuellement une
# annale dont la faculté n'a pas pu être extraite automatiquement. Liste non
# garantie exhaustive/à jour — "Autre" reste toujours disponible en saisie libre.
UNIVERSITES = [
    "Aix-Marseille Université",
    "Université d'Angers",
    "Université de Bordeaux",
    "Université de Brest (UBO)",
    "Université de Caen Normandie",
    "Université Clermont Auvergne",
    "Université de Bourgogne (Dijon)",
    "Université Grenoble Alpes",
    "Université de Lille",
    "Université de Limoges",
    "Université Claude Bernard Lyon 1",
    "Université de Montpellier",
    "Université de Nantes",
    "Université Côte d'Azur (Nice)",
    "Université Paris Cité",
    "Sorbonne Université (Paris)",
    "Université Paris-Saclay",
    "Université Sorbonne Paris Nord (Bobigny)",
    "Université de Versailles Saint-Quentin-en-Yvelines (UVSQ)",
    "Université de Picardie Jules Verne (Amiens)",
    "Université de Poitiers",
    "Université de Reims Champagne-Ardenne",
    "Université de Rennes 1",
    "Université de Rouen Normandie",
    "Université Jean Monnet (Saint-Étienne)",
    "Université de Strasbourg",
    "Université Toulouse III - Paul Sabatier",
    "Université de Tours",
    "Université de Franche-Comté (Besançon)",
    "Université de Lorraine (Nancy)",
    "Université des Antilles",
    "Université de La Réunion",
]


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
    return sorted(path for path in VERIFIED_DIR.rglob("*.json") if path.name != ".imported.json")


def _exam_fingerprint(exam: UnessExam) -> str:
    """Content-based fingerprint (not `question.id`): Moodle assigns a fresh
    attempt-instance id to every question on each visit to the same annale
    URL, so two re-scrapes of the exact same quiz otherwise get different
    ids and silently bypass the `imported` dedup set, duplicating every
    quiz on each re-import."""
    import hashlib
    question_signatures = [
        q.enonce.strip() + "||" + "|".join(p.texte.strip() for p in q.propositions)
        for q in exam.questions
    ]
    raw = f"{exam.faculty}|{exam.level}|{exam.year}|{exam.title}|" + "|".join(question_signatures)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _staged_image_paths(exam: UnessExam) -> list[str]:
    """`local_path` values (e.g. "uness-<stamp>/images/<file>") for every image
    attached to `exam`, question-level and leftover dossier-level alike."""
    paths = [image.local_path for question in exam.questions for image in question.images if image.local_path]
    for image in exam.dp_context.get("images", []) or []:
        local_path = image.get("local_path") if isinstance(image, dict) else None
        if local_path:
            paths.append(local_path)
    return paths


def _cleanup_staged_images(exam: UnessExam) -> None:
    """Delete this exam's convenience copy under UNESS/images/<stamp>/ (see
    collector.py) now that it's been imported — the permanent copy under
    ARTIFACT_DIR, which the app actually serves images from, is untouched. A
    bridge can bundle several quizzes sharing one <stamp> folder, so this only
    removes the files this specific exam used, and the folder itself once empty."""
    staging_root = UNESS_ROOT / "images"
    touched_dirs: set[Path] = set()
    for local_path in _staged_image_paths(exam):
        parts = Path(local_path).parts
        if len(parts) != 3 or parts[1] != "images" or not parts[0].startswith("uness-"):
            continue
        staged_file = staging_root / parts[0].removeprefix("uness-") / parts[2]
        try:
            staged_file.unlink(missing_ok=True)
        except OSError:
            continue
        touched_dirs.add(staged_file.parent)
    for directory in touched_dirs:
        try:
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
        except OSError:
            pass


def format_annale_title(matiere: str | None, faculte: str | None, annee: int | None, raw_title: str | None = None) -> str:
    """Format title according to the standard convention: Matière — Université — Année."""
    parts = []
    if matiere and matiere.strip():
        parts.append(matiere.strip())
    if faculte and faculte.strip():
        parts.append(faculte.strip())
    if annee:
        parts.append(str(annee))
    if parts:
        return " — ".join(parts)
    clean_raw = str(raw_title or "").strip()
    return clean_raw if clean_raw else "Annale UNESS"


def _annale_group_title(exam: UnessExam) -> str:
    """Recover and format standard title."""
    raw = exam.title.rsplit(" — ", 1)[0] if " — " in exam.title else exam.title
    matiere = str(exam.metadata.get("subject", "")).strip() or raw
    return format_annale_title(matiere, exam.faculty, exam.year, raw)


def _load_exams_from_verified_file(path: Path) -> list[UnessExam]:
    """Accept both already-canonical exam files and raw AI (ChatGPT/Gemini) responses,
    auto-converting the latter by matching them against a pending bridge file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if is_raw_ai_response(payload):
        try:
            return convert_raw_payload(payload, [TO_REVIEW_DIR])
        except ValueError:
            return convert_raw_payload(payload, [TO_REVIEW_DIR, ARCHIVE_DIR])
    return [UnessExam.from_dict(payload)]


def _group_files_by_source_url(
    paths: list[Path],
) -> tuple[dict[str, list[tuple[Path, UnessExam]]], list[dict[str, str]]]:
    groups: dict[str, list[tuple[Path, UnessExam]]] = {}
    errors: list[dict[str, str]] = []
    for path in paths:
        try:
            exams = _load_exams_from_verified_file(path)
        except (ValueError, OSError, KeyError) as exc:
            errors.append({"file": path.name, "error": str(exc)})
            continue
        for exam in exams:
            source_url = str(exam.provenance.get("source_url", "")).strip()
            groups.setdefault(source_url, []).append((path, exam))
    return groups, errors


def import_verified_directory(
    tags: dict[str, str] | None = None, matieres: dict[str, str] | None = None
) -> dict[str, Any]:
    """Validate and import all new verified outputs, grouped by partiel, without aborting the batch.

    `matieres` (source_url -> matière) lets the caller override the auto-detected
    subject (parsed from the UNESS breadcrumb, which is often wrong: it can pick up
    a category/session label like "Entraînements examens DFASM2..." instead of the
    real subject) with a value the user picked against the canonical collège list —
    so a freshly-created annale is linked from the start instead of needing a manual
    correction via the edit form afterward."""
    tags = tags or {}
    matieres = matieres or {}
    index_path = VERIFIED_DIR / ".imported.json"
    try:
        imported = set(json.loads(index_path.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError, TypeError):
        imported = set()
    result: dict[str, Any] = {"imported": [], "skipped": [], "errors": [], "pending_tag": []}
    groups, load_errors = _group_files_by_source_url(scan_verified_exams())
    result["errors"].extend(load_errors)
    archived_paths: set[Path] = set()

    for source_url, entries in groups.items():
        annale = local_store.get_uness_annale_by_source_url(source_url) if source_url else None
        if annale is None and source_url:
            type_annale = tags.get(source_url)
            if type_annale is None:
                first_path, first_exam = entries[0]
                # Ignorer si aucun fichier d'examen valide dans ce groupe
                if entries:
                    result["pending_tag"].append(
                        {
                            "source_url": source_url,
                            "faculte": first_exam.faculty,
                            "niveau": first_exam.level,
                            "annee": first_exam.year,
                            "matiere": str(first_exam.metadata.get("subject", "")),
                            "titre": _annale_group_title(first_exam),
                            "files": sorted({path.name for path, _ in entries}),
                        }
                    )
                continue
            _, first_exam = entries[0]
            matiere = matieres.get(source_url) or str(first_exam.metadata.get("subject", ""))
            titre = (
                format_annale_title(matiere, first_exam.faculty, first_exam.year, first_exam.title)
                if matieres.get(source_url)
                else _annale_group_title(first_exam)
            )
            annale_id = local_store.create_uness_annale(
                source_url=source_url,
                collected_at=str(first_exam.provenance.get("collected_at", "")).strip(),
                faculte=first_exam.faculty,
                niveau=first_exam.level,
                annee=first_exam.year,
                matiere=matiere,
                titre=titre,
                type_annale=type_annale,
            )
            annale = local_store.get_uness_annale(annale_id)

        # Re-scraping the same annale URL gives every question a fresh Moodle
        # attempt-instance id and lets Gemini reword its correction, so neither
        # `question.id` nor a content hash of the AI's answer reliably identifies
        # "the same quiz already imported here" — but the quiz title extracted
        # from the (stable) Moodle HTML does, so check against what's already
        # attached to this annale before falling back to the fingerprint set.
        existing_titles = (
            {s["course_title"] for s in local_store.list_annale_sessions(annale["id"])}
            if annale is not None
            else set()
        )

        for path, exam in entries:
            try:
                if annale is not None and exam.title in existing_titles:
                    result["skipped"].append(path.name)
                    continue
                fingerprint = _exam_fingerprint(exam)
                if fingerprint in imported:
                    result["skipped"].append(path.name)
                    continue
                session_id = import_uness_exam(exam, matiere=annale["matiere"] if annale is not None else "")
                if annale is not None:
                    local_store.set_session_annale_id(session_id, annale["id"])
                imported.add(fingerprint)
                _cleanup_staged_images(exam)
                result["imported"].append(
                    {"file": path.name, "session_id": session_id, "disagreements": count_disagreements(exam)}
                )
                if path not in archived_paths:
                    # Determine subfolder relative to VERIFIED_DIR (or use slugified course title)
                    rel_subfolder = path.parent.relative_to(VERIFIED_DIR) if path.is_relative_to(VERIFIED_DIR) and path.parent != VERIFIED_DIR else Path(_slug(exam.faculty or exam.title or "partiel"))
                    target_archive_dir = ARCHIVE_DIR / rel_subfolder
                    target_archive_dir.mkdir(parents=True, exist_ok=True)

                    path.replace(target_archive_dir / path.name)
                    archived_paths.add(path)
                    collected_at = str(exam.provenance.get("collected_at", "")).strip()
                    for candidate in list(TO_REVIEW_DIR.rglob("*.json")):
                        try:
                            source = json.loads(candidate.read_text(encoding="utf-8")).get("source", {})
                        except (OSError, json.JSONDecodeError, AttributeError):
                            continue
                        if collected_at and source.get("collected_at") == collected_at:
                            cand_parent = candidate.parent
                            if cand_parent != TO_REVIEW_DIR:
                                cand_subfolder = cand_parent.relative_to(TO_REVIEW_DIR)
                                cand_target_dir = ARCHIVE_DIR / cand_subfolder
                                cand_target_dir.mkdir(parents=True, exist_ok=True)
                                # Déplacer TOUS les fichiers du dossier de session (JSONs + images)
                                for file_item in list(cand_parent.iterdir()):
                                    if file_item.is_file():
                                        target_file = cand_target_dir / file_item.name
                                        file_item.replace(target_file)
                                try:
                                    cand_parent.rmdir()
                                except OSError:
                                    pass
                            else:
                                cand_target_dir = ARCHIVE_DIR / rel_subfolder
                                cand_target_dir.mkdir(parents=True, exist_ok=True)
                                candidate.replace(cand_target_dir / f"a_verifier-{candidate.name}")
                    path_parent = path.parent
                    if path_parent != VERIFIED_DIR and path_parent.is_dir() and not any(path_parent.iterdir()):
                        try:
                            path_parent.rmdir()
                        except OSError:
                            pass
            except (ValueError, OSError, PermissionError) as exc:
                result["errors"].append({"file": path.name, "error": str(exc)})
            except Exception as exc:  # noqa: BLE001 - one bad exam must never abort the
                # whole import batch (same failure mode fixed in gemini_autocorrect's
                # per-quiz loop: an exception type outside the tuple above used to
                # propagate out of the loop and silently drop every file still queued
                # after this one).
                logger.exception(f"import_verified_directory: erreur inattendue sur {path.name!r}")
                result["errors"].append({"file": path.name, "error": f"Erreur inattendue : {exc}"})

    index_path.write_text(json.dumps(sorted(imported), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    logger.info(
        f"import_verified_directory: {len(result['imported'])} importé(s), "
        f"{len(result['skipped'])} ignoré(s), {len(result['pending_tag'])} en attente de matière, "
        f"{len(result['errors'])} erreur(s)"
    )
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
        refs.append(f"{exam.provenance.get('source', 'UNESS')}: {artifact}")
    return list(dict.fromkeys(ref for ref in refs if ref))


def _question_metadata(question: UnessQuestion, exam: UnessExam) -> dict[str, Any]:
    source_label = str(exam.provenance.get("source", "UNESS")).strip() or "UNESS"
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
        primary_source = source_label.lower()
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
                    "item_numbers": list(question.item_numbers),
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
                "source": source_label,
                "official": source_label.upper() == "UNESS",
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
        "item_numbers": tuple(question.item_numbers),
        "item_classification_source": "source" if question.item_numbers else "",
        "item_classification_confidence": 1.0 if question.item_numbers else 0.0,
        "item_classifier_version": "source-explicit-v1" if question.item_numbers else "",
        "allow_session_item_fallback": str(exam.provenance.get("source", "UNESS")).strip().lower() != "ednpro",
    }


def assert_verified_exam(exam: UnessExam) -> None:
    """Check that a verified exam has complete, coherent AI review metadata on
    every proposition — except questions marked "unsupported" (the model
    never received the image it needed): those only need the official UNESS
    answer as a fallback ground truth. Blocking the whole quiz over one such
    question would throw away every other question that WAS properly
    verified, which is worse than importing with one weaker question."""
    for question in exam.questions:
        if question.verification_status == "unsupported":
            if question.propositions and any(
                proposition.reponse_uness is None for proposition in question.propositions
            ):
                raise ValueError(
                    f"Question {question.id} : vérification visuelle indisponible et "
                    "réponse officielle UNESS manquante — impossible à importer."
                )
            continue
        for image in question.images:
            if image.metadata.get("verification_status") != "provided_to_ai":
                raise ValueError(f"Image {image.source_url} non analysée par l'IA (status image: {image.metadata.get('verification_status')}, doit être provided_to_ai)")
        for proposition in question.propositions:
            if proposition.verdict_ia is None:
                raise ValueError(f"verdict_ia (vérification IA) manquant pour la proposition {proposition.id}")
            if not proposition.explication_ia or not proposition.explication_ia.strip():
                raise ValueError(f"Explication de vérification IA manquante pour la proposition {proposition.id}")
            if proposition.confiance_ia is None or not (0.0 <= proposition.confiance_ia <= 1.0):
                raise ValueError(f"Confiance de vérification IA invalide pour la proposition {proposition.id}")
            if proposition.statut not in {"concordant", "desaccord", "incertain", "valide_manuellement"}:
                raise ValueError(f"Statut de vérification IA invalide ({proposition.statut}) pour la proposition {proposition.id}")
            if proposition.statut == "incertain" and proposition.reponse_uness is not None:
                raise ValueError(f"Statut de vérification IA incohérent ({proposition.statut}) pour la proposition {proposition.id}")


def _sanitize_unsupported_questions(exam: UnessExam) -> UnessExam:
    """Actively clear `verdict_ia`/`confiance_ia`/`explication_ia` on every
    proposition of an `unsupported` question, instead of trusting that the
    file already arrived that way.

    `gemini_conversion._question` and `ai_verifier._unsupported_visual_question`
    both already clear these fields for the two in-app producers of verified
    exam files — but `VERIFIED_DIR` is also a supported trust boundary for
    files this app never produced (a canonical exam JSON dropped there by
    hand, e.g. via "Scanner les JSON vérifiés" on /annales). Such a file could
    claim `verification_status: "unsupported"` while still carrying an intact
    `verdict_ia` the model produced without ever seeing the required image.
    `assert_verified_exam`'s `unsupported` branch only checks that
    `reponse_uness` is present — it does not re-derive these fields — so this
    function is what actually guarantees "le verdict IA est honnêtement vidé"
    regardless of what the source file contains, rather than that invariant
    holding only by convention in the two producers."""
    sanitized_questions = []
    for question in exam.questions:
        if question.verification_status != "unsupported":
            sanitized_questions.append(question)
            continue
        sanitized_propositions = tuple(
            dataclasses.replace(
                proposition,
                verdict_ia=None,
                explication_ia=UNSUPPORTED_VISUAL_EXPLANATION,
                confiance_ia=None,
            )
            for proposition in question.propositions
        )
        sanitized_questions.append(dataclasses.replace(question, propositions=sanitized_propositions))
    return dataclasses.replace(exam, questions=tuple(sanitized_questions))


def _classify_exam_items(exam: UnessExam, matiere: str) -> tuple[str, tuple[str, ...]]:
    """Détermine le(s) item(s) EDN d'un examen UNESS via classification IA bon
    marché, bornée aux items candidats de sa matière — entrainement.uness.fr
    n'expose jamais lui-même de numéro d'item (vérifié en amont du pipeline).
    Dégrade silencieusement vers "non classifié" (comme avant cette fonction)
    en cas d'échec réseau/IA plutôt que de bloquer l'import."""
    from backend.core.uness.item_classifier import classify_exam_items

    effective_matiere = matiere or str(exam.metadata.get("subject", ""))
    context_text = str(exam.dp_context.get("enonce_general", "")) if exam.dp_context else ""
    try:
        result = classify_exam_items(exam.title, effective_matiere, context_text)
    except Exception as exc:
        logger.warning(f"_classify_exam_items({exam.title!r}) échoué : {exc}")
        return "", ()
    if not result.confident or not result.item_numbers:
        return "", ()
    return result.item_numbers[0], result.item_numbers


def import_uness_exam(exam: UnessExam, *, matiere: str = "") -> int:
    """Create one local, replayable practice session from a verified UNESS exam.

    `matiere` : matière qualifiée par l'utilisateur pour l'annale de cet examen
    (restreint les items candidats de la classification IA). À défaut, retombe
    sur `exam.metadata["subject"]` (auto-détecté, moins fiable).
    """
    _assert_no_sensitive_data(exam.to_dict())
    exam = _sanitize_unsupported_questions(exam)
    assert_verified_exam(exam)
    if not exam.questions:
        raise ValueError("L'examen UNESS ne contient aucune question importable")
    if str(exam.provenance.get("source", "")).strip().lower() == "ednpro":
        from backend.core.uness.question_item_classifier import classify_exam_questions

        exam = classify_exam_questions(exam, matiere or str(exam.metadata.get("subject", "")))
    questions = [_to_practice_question(question, exam) for question in exam.questions]
    closed = sum(question["kind"] is QuestionKind.CLOSED for question in questions)

    item_number = _session_value(exam, "item_number")
    item_numbers: tuple[str, ...] = (item_number,) if item_number else ()
    if not item_number and str(exam.provenance.get("source", "")).strip().lower() == "ednpro":
        item_numbers = tuple(dict.fromkeys(
            item for question in exam.questions for item in question.item_numbers
        ))
        item_number = item_numbers[0] if item_numbers else ""
    elif not item_number:
        item_number, item_numbers = _classify_exam_items(exam, matiere)

    spec = PracticeSessionSpec(
        practice_kind=_practice_kind(exam),
        total_questions=len(questions),
        open_questions=len(questions) - closed,
        closed_questions=closed,
        course_id=_session_value(exam, "course_id"),
        course_title=exam.title,
        item_number=item_number,
        item_numbers=item_numbers,
        difficulty=PracticeDifficulty.EDN,
    )
    return local_store.create_ai_practice_session(spec=spec, questions=questions, model="uness-verified-local")


def import_source_exam(exam: UnessExam, *, source: str, matiere: str = "") -> int:
    """Import any source-compatible exam and attach it to a typed annale group.

    The legacy function remains the UNESS-compatible session importer; this
    facade adds source provenance and lets EDNpro reuse the same QCM storage.
    """
    source_url = str(exam.provenance.get("source_url", "")).strip()
    if not source_url:
        raise ValueError("Une source_url est requise pour un import multi-source")
    if not exam.questions:
        raise ValueError("L'examen source ne contient aucune question importable")
    subject = matiere or str(exam.metadata.get("subject", ""))
    annale = local_store.get_uness_annale_by_source_url(source_url)
    if annale is None and exam.title and (exam.year is not None or subject):
        annale = local_store.get_uness_annale_by_identity(
            source=source,
            annee=exam.year,
            matiere=subject,
            titre=exam.title,
        )
    if annale is None:
        annale_id = local_store.create_uness_annale(
            source_url=source_url,
            collected_at=str(exam.provenance.get("collected_at", "")),
            faculte=exam.faculty,
            niveau=exam.level,
            annee=exam.year,
            matiere=subject,
            titre=exam.title,
            type_annale=str(exam.metadata.get("exam_type", "edn_complet")),
            source=source,
            source_exam_id=str(exam.provenance.get("external_exam_id", "")),
            metadata_json=json.dumps(exam.metadata, ensure_ascii=False),
        )
    else:
        annale_id = int(annale["id"])
    source_name = str(exam.provenance.get("source", source)).strip().lower()
    sub_exams = [exam]
    if source_name == "ednpro" and exam.metadata.get("dossiers"):
        question_by_dossier: dict[str, list[UnessQuestion]] = {}
        for question in exam.questions:
            dossier_id = str(question.dp_context.get("dossier_id") or "").strip()
            question_by_dossier.setdefault(dossier_id, []).append(question)
        grouped: list[UnessExam] = []
        assigned: set[str] = set()
        for dossier in exam.metadata.get("dossiers", []):
            dossier_id = str(dossier.get("id") or "").strip()
            questions = question_by_dossier.get(dossier_id, [])
            if not questions:
                continue
            number = dossier.get("numero")
            kind = str(dossier.get("type") or "Dossier").strip()
            label = f"{kind} {number}" if number is not None else kind
            metadata = dict(exam.metadata)
            metadata["dossiers"] = [dossier]
            grouped.append(dataclasses.replace(
                exam,
                title=f"{exam.title} · {label}",
                questions=tuple(questions),
                metadata=metadata,
            ))
            assigned.update(question.id for question in questions)
        remaining = tuple(question for question in exam.questions if question.id not in assigned)
        if remaining:
            grouped.append(dataclasses.replace(exam, questions=remaining, metadata={**exam.metadata, "dossiers": []}))
        if grouped:
            sub_exams = grouped

    imported_session_ids = []
    for sub_exam in sub_exams:
        session_id = import_uness_exam(sub_exam, matiere=subject)
        local_store.set_session_annale_id(session_id, annale_id)
        imported_session_ids.append(session_id)
    return imported_session_ids[0]


def count_disagreements(exam: UnessExam) -> int:
    """Count proposition-level IA/official disagreements for the import response."""
    return sum(
        proposition.statut == "desaccord"
        for question in exam.questions
        for proposition in question.propositions
    )
