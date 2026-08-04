import json

import pytest


def test_normalize_ednpro_payload_marks_tierce_non_official_source():
    from backend.core.ednpro.normalizer import normalize_ednpro_payload

    exam = normalize_ednpro_payload(
        {
            "title": "EDN 2023 — P1",
            "year": 2023,
            "session_id": "2023-p1",
            "url": "https://ednpro.app/annales/2023-p1",
            "subject": "Cardiologie",
            "questions": [
                {
                    "id": "q-1",
                    "type": "QRU",
                    "stem": "Quel est le diagnostic ?",
                    "choices": [
                        {"id": "a", "text": "Réponse A", "correct": True},
                        {"id": "b", "text": "Réponse B", "correct": False},
                    ],
                    "explanation": "Explication EDNpro.",
                    "item_numbers": ["221"],
                }
            ],
        }
    )

    assert exam.provenance["source"] == "EDNpro"
    assert exam.metadata["correction_source"] == "ednpro"
    assert exam.metadata["correction_official"] is False
    assert exam.metadata["session_id"] == "2023-p1"
    assert exam.questions[0].propositions[0].reponse_uness is True
    assert exam.questions[0].item_numbers == ("221",)


def test_normalize_ednpro_payload_rejects_sensitive_urls():
    from backend.core.ednpro.normalizer import normalize_ednpro_payload

    with pytest.raises(ValueError, match="sensible"):
        normalize_ednpro_payload(
            {
                "title": "EDN 2023",
                "year": 2023,
                "url": "https://ednpro.app/annales/1?token=secret",
                "questions": [],
            }
        )


def test_normalize_ednpro_payload_preserves_video_page_refs():
    from backend.core.ednpro.normalizer import normalize_ednpro_payload

    exam = normalize_ednpro_payload(
        {
            "title": "EDN 2023",
            "year": 2023,
            "url": "https://ednpro.app/annales/1",
            "questions": [],
            "resources": [
                {
                    "title": "ECG — Item 221",
                    "url": "https://ednpro.app/videos/221",
                    "type": "video",
                    "item_numbers": ["221"],
                }
            ],
        }
    )

    assert exam.metadata["resources"][0]["url"] == "https://ednpro.app/videos/221"
