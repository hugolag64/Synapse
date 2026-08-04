import json
from pathlib import Path

from backend.core.reviews import local_store
from backend.core.ai.routing import AIModel, AIResponse
from backend.core.uness.models import UnessExam


def _exam() -> UnessExam:
    return UnessExam.from_dict(
        {
            "faculty": "EDNpro",
            "level": "EDN",
            "year": 2023,
            "title": "EDN 2023 — P1",
            "questions": [],
            "provenance": {
                "source": "EDNpro",
                "source_url": "https://ednpro.app/annales/2023-p1",
                "collected_at": "2026-08-04T08:00:00+00:00",
                "collection_status": "corrected",
                "external_exam_id": "2023-p1",
            },
            "metadata": {"subject": "Cardiologie", "exam_type": "edn_complet"},
        }
    )


def test_import_source_exam_creates_ednpro_annale_group(monkeypatch):
    from backend.core.uness import import_service

    monkeypatch.setattr(import_service, "import_uness_exam", lambda exam, matiere="": 321)

    session_id = import_service.import_source_exam(_exam(), source="EDNpro", matiere="Cardiologie")

    assert session_id == 321
    annale = local_store.get_uness_annale_by_source_url("https://ednpro.app/annales/2023-p1")
    assert annale["source"] == "EDNpro"
    assert annale["type_annale"] == "edn_complet"
    assert annale["source_exam_id"] == "2023-p1"


def _source_payload() -> dict:
    return {
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
            }
        ],
    }


def test_generate_and_import_writes_canonical_json_after_ai_correction(monkeypatch, tmp_path):
    from backend.core.ednpro.ai_pipeline import generate_and_import_ednpro

    ai_payload = {
        "questions": [
            {
                "id": "q-1",
                "verification_status": "verified",
                "propositions": [
                    {"id": "a", "verdict_ia": True, "explication": "A est vraie.", "confiance_ia": 0.95},
                    {"id": "b", "verdict_ia": False, "explication": "B est fausse.", "confiance_ia": 0.95},
                ],
            }
        ]
    }

    class FakeService:
        def generate(self, *args, **kwargs):
            return AIResponse(json.dumps(ai_payload), AIModel.FLASH_LITE, 10, 20)

    captured = {}

    def fake_import(exam, *, source, matiere):
        captured.update(exam=exam, source=source, matiere=matiere)
        return 777

    monkeypatch.setattr("backend.core.ednpro.ai_pipeline.import_service.import_source_exam", fake_import)
    output = tmp_path / "ednpro-2023-p1.json"

    result = generate_and_import_ednpro(_source_payload(), service=FakeService(), output_path=output)

    assert result["session_id"] == 777
    assert Path(result["json_path"]).is_file()
    assert json.loads(output.read_text(encoding="utf-8"))["provenance"]["source"] == "EDNpro"
    assert captured["exam"].questions[0].propositions[0].verdict_ia is True


def test_question_metadata_labels_ednpro_as_non_official_source():
    from backend.core.ednpro.normalizer import normalize_ednpro_payload
    from backend.core.uness import import_service

    exam = normalize_ednpro_payload(_source_payload() | {
        "questions": [{
            **_source_payload()["questions"][0],
            "choices": [
                {"id": "a", "text": "Réponse A", "correct": True, "ai_verdict": True, "ai_explanation": "A", "ai_confidence": 0.9},
                {"id": "b", "text": "Réponse B", "correct": False, "ai_verdict": False, "ai_explanation": "B", "ai_confidence": 0.9},
            ],
        }]
    })

    metadata = import_service._question_metadata(exam.questions[0], exam)

    assert metadata["correction"]["official"]["source"] == "EDNpro"
    assert metadata["correction"]["official"]["official"] is False


def test_ednpro_session_import_uses_question_level_item_classifier(monkeypatch):
    from backend.core.ednpro.normalizer import normalize_ednpro_payload
    from backend.core.uness import import_service

    payload = _source_payload()
    payload["questions"][0]["choices"] = [
        {"id": "a", "text": "A", "correct": True, "ai_verdict": True, "ai_explanation": "A", "ai_confidence": 0.9},
        {"id": "b", "text": "B", "correct": False, "ai_verdict": False, "ai_explanation": "B", "ai_confidence": 0.9},
    ]
    payload["questions"][0].pop("item_numbers", None)
    exam = normalize_ednpro_payload(payload)
    captured = {}

    def fake_create(*, spec, questions, model):
        captured["questions"] = questions
        return 888

    monkeypatch.setattr(import_service.local_store, "create_ai_practice_session", fake_create)
    monkeypatch.setattr(
        "backend.core.uness.question_item_classifier.classify_exam_questions",
        lambda exam, matiere: exam.__class__(**{
            **exam.__dict__,
            "questions": (exam.questions[0].__class__(**{
                **exam.questions[0].__dict__, "item_numbers": ("221",)
            }),),
        }),
    )

    assert import_service.import_uness_exam(exam) == 888
    assert captured["questions"][0]["item_numbers"] == ("221",)


def test_ednpro_import_indexes_explicit_video_resources(monkeypatch, tmp_path):
    from backend.core.ednpro.ai_pipeline import generate_and_import_ednpro
    from backend.core.prep.resources import list_prep_resources_for_item

    payload = _source_payload()
    payload["resources"] = [{
        "title": "Athérome en vidéo",
        "url": "https://ednpro.app/videos/221",
        "type": "video",
        "item_numbers": ["221"],
    }]
    payload["questions"][0]["choices"] = [
        {"id": "a", "text": "A", "correct": True, "ai_verdict": True, "ai_explanation": "A", "ai_confidence": 0.9},
        {"id": "b", "text": "B", "correct": False, "ai_verdict": False, "ai_explanation": "B", "ai_confidence": 0.9},
    ]

    class FakeService:
        def generate(self, *args, **kwargs):
            return AIResponse(json.dumps({
                "questions": [{
                    "id": "q-1", "verification_status": "verified",
                    "propositions": [
                        {"id": "a", "verdict_ia": True, "explication": "A", "confiance_ia": 0.9},
                        {"id": "b", "verdict_ia": False, "explication": "B", "confiance_ia": 0.9},
                    ],
                }]
            }), AIModel.FLASH_LITE, 1, 1)

    monkeypatch.setattr("backend.core.ednpro.ai_pipeline.import_service.import_source_exam", lambda *args, **kwargs: 1)
    generate_and_import_ednpro(payload, service=FakeService(), output_path=tmp_path / "exam.json")

    assert list_prep_resources_for_item("221")[0]["title"] == "Athérome en vidéo"
