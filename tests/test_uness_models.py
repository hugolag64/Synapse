from __future__ import annotations

import json

import pytest

from backend.core.uness.json_io import load_exam, save_exam
from backend.core.uness.models import UnessExam


def test_exam_round_trip_preserves_uness_correction_ai_verdict_and_visual_context(tmp_path) -> None:
    """Catches a serializer that drops metadata or conflates official and IA answers."""
    payload = {
        "faculty": "Universit\u00e9 Paris Cité",
        "level": "DFASM3",
        "year": 2026,
        "title": "Gériatrie — dossier progressif",
        "provenance": {"source": "UNESS", "artifact_path": "imports/exam-42.json"},
        "dp_context": {"patient": "Mme Martin, 86 ans", "step": 2},
        "questions": [
            {
                "id": "q-1",
                "type_question": "QRM",
                "enonce": "Quels éléments orientent vers une dénutrition ?",
                "support_visuel_seul": True,
                "images": [
                    {
                        "source_url": "https://uness.example/scan.png",
                        "local_path": "imports/media/scan.png",
                        "alt_text": "Courbe pondérale",
                        "metadata": {"width": 1200, "height": 800},
                    }
                ],
                "propositions": [
                    {
                        "id": "A",
                        "texte": "Perte de poids involontaire",
                        "reponse_uness": True,
                        "verdict_ia": False,
                        "reponse_finale": None,
                        "statut": "desaccord",
                    }
                ],
            }
        ],
    }

    exam = UnessExam.from_dict(payload)
    target = tmp_path / "exam.json"
    save_exam(exam, target)

    persisted = json.loads(target.read_text(encoding="utf-8"))
    assert persisted["schema_version"] == 1
    assert persisted["faculty"] == "Universit\u00e9 Paris Cité"
    assert persisted["questions"][0]["propositions"][0] == {
        "id": "A",
        "texte": "Perte de poids involontaire",
        "reponse_uness": True,
        "verdict_ia": False,
        "reponse_finale": None,
        "statut": "desaccord",
    }
    assert load_exam(target).to_dict() == persisted


@pytest.mark.parametrize("type_question", ["QRM", "QRU", "QRP/L", "DP", "KFP", "QROC"])
def test_exam_accepts_every_supported_question_type(type_question: str) -> None:
    """Catches validation that rejects one of the supported UNESS question kinds."""
    exam = UnessExam.from_dict(
        {"questions": [{"id": "q1", "type_question": type_question, "enonce": "Question"}]}
    )

    assert exam.questions[0].type_question == type_question


def test_exam_rejects_unknown_status_and_question_type() -> None:
    """Catches imports that silently accept values downstream consumers cannot interpret."""
    with pytest.raises(ValueError, match="statut"):
        UnessExam.from_dict(
            {
                "questions": [
                    {
                        "id": "q1",
                        "type_question": "QRM",
                        "enonce": "Question",
                        "propositions": [{"id": "A", "texte": "Réponse", "statut": "invalide"}],
                    }
                ]
            }
        )

    with pytest.raises(ValueError, match="type_question"):
        UnessExam.from_dict(
            {"questions": [{"id": "q1", "type_question": "QCM", "enonce": "Question"}]}
        )
