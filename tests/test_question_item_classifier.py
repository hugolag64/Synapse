from dataclasses import replace

from backend.core.uness.models import UnessExam, UnessQuestion


def _exam() -> UnessExam:
    return UnessExam.from_dict({
        "faculty": "EDNpro", "level": "EDN", "year": 2023, "title": "EDN 2023",
        "questions": [
            {"id": "q-source", "type_question": "QRU", "enonce": "Item 221", "item_numbers": ["221"]},
            {"id": "q-ai", "type_question": "QRU", "enonce": "Facteurs de risque cardiovasculaire"},
        ],
        "provenance": {
            "source": "EDNpro", "source_url": "https://ednpro.app/annales/1",
            "collected_at": "2026-08-04T08:00:00+00:00", "collection_status": "corrected",
        },
        "metadata": {"subject": "Cardiologie"},
    })


def test_explicit_source_item_is_kept_without_ai_call(monkeypatch):
    from backend.core.uness import question_item_classifier

    monkeypatch.setattr(question_item_classifier, "classify_exam_items", lambda *args: (_ for _ in ()).throw(AssertionError()))

    result = question_item_classifier.classify_exam_questions(_exam(), "Cardiologie")

    assert result.questions[0].item_numbers == ("221",)


def test_missing_question_uses_bounded_ai_classification(monkeypatch):
    from backend.core.uness import question_item_classifier
    from backend.core.uness.item_classifier import ItemClassification

    monkeypatch.setattr(
        question_item_classifier,
        "classify_exam_items",
        lambda title, matiere, context_text="": ItemClassification(("222",), True),
    )

    result = question_item_classifier.classify_exam_questions(_exam(), "Cardiologie")

    assert result.questions[1].item_numbers == ("222",)


def test_exam_level_import_drops_item_numbers_when_classifier_is_not_confident(monkeypatch):
    from backend.core.uness import import_service
    from backend.core.uness.item_classifier import ItemClassification

    monkeypatch.setattr(
        "backend.core.uness.item_classifier.classify_exam_items",
        lambda *args, **kwargs: ItemClassification(("222",), False),
    )

    assert import_service._classify_exam_items(_exam(), "Cardiologie") == ("", ())
