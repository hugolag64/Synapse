import json

import pytest

from backend.core.practice.importer import (
    ImportValidationError,
    parse_practice_bank,
    parse_practice_discussion,
    suggest_item_numbers,
)
from backend.core.practice.models import PracticeKind, PracticeSessionSpec
from backend.core.reviews import local_store


@pytest.fixture()
def practice_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "practice-import.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def _payload():
    return {
        "version": 1,
        "source": "ChatGPT · base DP juillet 2026",
        "cases": [{
            "id": "dp-115-001",
            "kind": "dp",
            "title": "Dyspnée aiguë",
            "item_numbers": ["115"],
            "stem": "Un patient consulte pour dyspnée.",
            "questions": [{
                "prompt": "Quelle est la première décision ?",
                "choices": ["A", "B"],
                "answer": "A",
                "explanation": "La priorité est...",
            }],
        }],
    }


def test_parser_accepts_structured_dp_and_preserves_provenance():
    batch = parse_practice_bank(json.dumps(_payload(), ensure_ascii=False))
    assert batch.source == "ChatGPT · base DP juillet 2026"
    assert batch.cases[0].kind == "dp"
    assert batch.cases[0].item_numbers == ("115",)
    assert batch.cases[0].questions[0].answer == "A"
    assert batch.cases[0].status == "ready"


def test_parser_marks_missing_item_as_review():
    payload = _payload()
    payload["cases"][0]["item_numbers"] = []
    batch = parse_practice_bank(payload)
    assert batch.cases[0].status == "needs_review"
    assert "ITEM" in batch.cases[0].review_reason


def test_parser_rejects_unsupported_case_type():
    payload = _payload()
    payload["cases"][0]["kind"] = "tcs"
    with pytest.raises(ImportValidationError, match="QCM, DP ou KFP"):
        parse_practice_bank(payload)


def test_discussion_parser_extracts_questions_answers_and_explanations():
    discussion = """
    Discussion ChatGPT — ITEM 115 et ITEM 222
    Question 1 : Quel est le diagnostic principal ?
    Réponse : A — insuffisance cardiaque.
    Explication : Les signes cliniques orientent vers ce diagnostic.

    Question 2 : Quel examen demander ?
    Réponse : B — échocardiographie.
    Explication : Il confirme la dysfonction cardiaque.
    """
    batch = parse_practice_discussion(discussion, source="chatgpt.txt")
    case = batch.cases[0]
    assert case.kind == "dp"
    assert len(case.questions) == 2
    assert case.questions[0].answer.startswith("A")
    assert case.item_numbers == ("115", "222")
    assert case.status == "needs_review"


def test_discussion_parser_supports_html_and_kfp_marker():
    html = "<h1>KFP ITEM 330</h1><p>Question 1 : Conduite ?</p><p>Réponse : ABC</p><p>Explication : Priorité.</p>"
    batch = parse_practice_discussion(html, source="discussion.html")
    assert batch.cases[0].kind == "kfp"
    assert batch.cases[0].item_numbers == ("330",)


def test_discussion_parser_imports_qcm_by_item_with_choices():
    discussion = """
    QCM — ITEM 115
    Question 1 : Quels signes évoquent une insuffisance cardiaque ?
    A. Dyspnée
    B. Fièvre isolée
    C. Orthopnée
    Réponse : A, C
    Explication : La dyspnée et l'orthopnée sont caractéristiques.
    """
    batch = parse_practice_discussion(discussion, source="qcm-chatgpt.md")
    case = batch.cases[0]
    assert case.kind == "qcm"
    assert case.item_numbers == ("115",)
    assert case.questions[0].choices == ("A. Dyspnée", "B. Fièvre isolée", "C. Orthopnée")
    assert case.questions[0].answer == "A, C"


def test_item_suggestions_rank_title_matches():
    catalog = [("115", "Insuffisance cardiaque"), ("330", "Prescription"), ("222", "Facteurs de risque")]
    assert suggest_item_numbers("facteurs de risque cardiovasculaire", catalog)[0][0] == "222"


def test_import_persists_case_and_deduplicates(practice_db):
    batch = parse_practice_bank(_payload())
    first = local_store.import_practice_batch(batch)
    second = local_store.import_practice_batch(batch)
    assert first == {"inserted": 1, "duplicates": 0, "needs_review": 0}
    assert second == {"inserted": 0, "duplicates": 1, "needs_review": 0}
    rows = local_store.get_imported_practice_cases(item_number="115")
    assert len(rows) == 1
    assert rows[0]["title"] == "Dyspnée aiguë"


def test_import_review_queue_contains_unassigned_case(practice_db):
    payload = _payload()
    payload["cases"][0]["item_numbers"] = []
    batch = parse_practice_bank(payload)
    local_store.import_practice_batch(batch)
    queue = local_store.get_import_review_queue()
    assert len(queue) == 1
    assert queue[0]["status"] == "needs_review"


def test_discussion_source_is_kept_for_provenance(practice_db):
    batch = parse_practice_discussion(
        "ITEM 115\nQuestion 1 : Diagnostic ?\nRéponse : A\nExplication : Raisonnement.",
        source="chatgpt-export.txt",
    )
    local_store.import_practice_batch(batch)
    row = local_store.get_imported_practice_cases()[0]
    assert row["source"] == "chatgpt-export.txt"
    assert "Diagnostic" in row["source_content"]


def test_local_bank_supports_random_cases_and_anchors(practice_db):
    batch = parse_practice_bank(_payload())
    local_store.import_practice_batch(batch)
    assert len(local_store.get_random_imported_practice_cases(item_number="115")) == 1
    question = local_store.get_imported_practice_cases(item_number="115")[0]["questions"][0]
    session_id = local_store.create_ai_practice_session(
        spec=PracticeSessionSpec(
            practice_kind=PracticeKind.DP, total_questions=1, open_questions=0,
            closed_questions=1, item_number="115", course_id="course-115",
            course_title="Insuffisance cardiaque",
        ),
        questions=[{"prompt": question["prompt"], "kind": "closed", "choices": ["A", "B"],
                    "answer": question["answer"], "explanation": question["explanation"]}],
        model="local-import",
    )
    ai_question = local_store.get_ai_practice_session(session_id)[0]
    local_store.set_ai_practice_anchor(ai_question["id"], "À revoir volontairement")
    assert local_store.get_ai_practice_anchors(item_number="115")[0]["question_id"] == ai_question["id"]
    local_store.remove_ai_practice_anchor(ai_question["id"])
    assert local_store.get_ai_practice_anchors(item_number="115") == []
