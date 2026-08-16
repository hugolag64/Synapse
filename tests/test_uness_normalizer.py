from __future__ import annotations

from pathlib import Path

import pytest

from backend.core.uness.artifacts import ExamMetadata, RawMedia, RawUnessArtifact
from backend.core.uness.normalizer import extract_review_content, normalize_artifact

FIXTURE = Path(__file__).parent / "fixtures" / "uness" / "geriatry_review.html"


def _metadata() -> ExamMetadata:
    return ExamMetadata(
        faculte="Université de Paris",
        niveau="DFASM3",
        matiere="Gériatrie",
        type_epreuve="Annale",
        annee=2026,
        titre="Gériatrie — évaluation nutritionnelle",
        source_url="https://entrainement.uness.example/course/review/42",
    )


def test_extract_review_content_preserves_visible_correction_score_context_and_image() -> None:
    """Catches parsers that lose the reviewed answer state or visual context."""
    questions = extract_review_content(FIXTURE.read_text(encoding="utf-8"))

    assert len(questions) == 1
    question = questions[0]
    assert question.id == "geri-qrm-1"
    assert question.type_question == "QRM"
    assert question.enonce == "Quels éléments sont des critères de dénutrition chez la personne âgée ?"
    assert question.dp_context == {
        "id": "dp-geriatrie-1",
        "text": "Dossier progressif — Évaluation nutritionnelle\nUne personne âgée vivant à domicile consulte pour une perte de poids récente.",
        "score_text": "Score : 1,00 / 1,00",
    }
    assert [(item.id, item.texte, item.reponse_uness) for item in question.propositions] == [
        ("A", "Perte de poids involontaire", True),
        ("B", "IMC supérieur à 30 kg/m²", False),
        ("C", "Diminution des apports alimentaires", True),
    ]
    assert question.images[0].source_url == "images/courbe-poids.png"
    assert question.images[0].alt_text == "Évolution pondérale sur six mois"
    assert question.images[0].caption == "Courbe pondérale"
    assert question.support_visuel_seul is True


def test_normalize_artifact_copies_media_under_a_per_exam_directory(tmp_path) -> None:
    """Catches imports that retain an image URL but do not preserve a local visual asset."""
    artifact = RawUnessArtifact(
        source_url="https://entrainement.uness.example/course/review/42",
        html_by_content={"nutrition": FIXTURE.read_text(encoding="utf-8")},
        media=[
            RawMedia(
                filename="courbe-poids.png",
                content=b"fixture-image",
                mime_type="image/png",
                question_number=1,
            )
        ],
        collected_at="2026-07-30T09:15:00+02:00",
        collection_status="complete",
        artifact_root=tmp_path,
    )

    exam = normalize_artifact(artifact, _metadata())

    image = exam.questions[0].images[0]
    copied_media = tmp_path / "geriatrie-evaluation-nutritionnelle" / "q01-courbe-poids.png"
    assert copied_media.read_bytes() == b"fixture-image"
    assert image.local_path == str(copied_media)
    assert image.source_url == "images/courbe-poids.png"
    assert exam.faculty == "Université de Paris"
    assert exam.provenance == {
        "source": "UNESS",
        "source_url": "https://entrainement.uness.example/course/review/42",
        "collected_at": "2026-07-30T09:15:00+02:00",
        "collection_status": "complete",
        "contents": ["nutrition"],
    }


def test_normalize_artifact_preserves_media_with_the_same_basename_from_different_paths(
    tmp_path,
) -> None:
    """Catches basename-only media maps that overwrite one visual with another."""
    artifact = RawUnessArtifact(
        source_url="https://entrainement.uness.example/course/review/42",
        html_by_content={
            "images": """
                <article class='review-question' data-question-id='q-images' data-question-type='QRM'>
                  <p class='question-text'>Identifier les examens</p>
                  <img src='images/a/scan.png' alt='Premier scanner'>
                  <img src='images/b/scan.png' alt='Second scanner'>
                </article>
            """
        },
        media=[
            RawMedia("images/a/scan.png", b"first", "image/png", question_number=1),
            RawMedia("images/b/scan.png", b"second", "image/png", question_number=1),
        ],
        collected_at="2026-07-30T09:15:00+02:00",
        collection_status="complete",
        artifact_root=tmp_path,
    )

    exam = normalize_artifact(artifact, _metadata())

    first, second = exam.questions[0].images
    assert first.local_path != second.local_path
    assert Path(first.local_path).read_bytes() == b"first"
    assert Path(second.local_path).read_bytes() == b"second"


def test_extract_review_content_sets_unknown_official_answer_when_no_correction_is_visible() -> None:
    """Catches an unchecked answer being mistaken for an official false correction."""
    questions = extract_review_content(
        """
        <article class='review-question' data-question-id='q-unreviewed' data-question-type='QRU'>
          <p class='question-text'>Question sans correction</p>
          <ul class='answers'><li class='answer'><span class='answer-label'>A.</span><span class='answer-text'>Proposition</span></li></ul>
        </article>
        """
    )

    assert questions[0].propositions[0].reponse_uness is None


def test_extract_review_content_preserves_explicit_question_rank():
    questions = extract_review_content(
        """
        <article class='review-question' data-question-id='q-ranked' data-question-type='QRU' data-rank='A'>
          <p class='question-text'>Question classée</p>
          <ul class='answers'><li class='answer correct'><span class='answer-label'>A.</span><span class='answer-text'>Proposition</span></li></ul>
        </article>
        """
    )

    assert questions[0].rank == "A"
    assert questions[0].rank_source == "official"


def test_normalize_artifact_rejects_a_metadata_url_that_does_not_match_the_capture() -> None:
    """Catches an artifact being attributed to a different user-confirmed source URL."""
    artifact = RawUnessArtifact(
        source_url="https://entrainement.uness.example/course/review/99",
        html_by_content={"nutrition": FIXTURE.read_text(encoding="utf-8")},
        media=[],
        collected_at="2026-07-30T09:15:00+02:00",
        collection_status="complete",
    )

    with pytest.raises(ValueError, match="source_url"):
        normalize_artifact(artifact, _metadata())
