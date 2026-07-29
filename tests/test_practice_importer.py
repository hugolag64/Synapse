import json

import pytest

from backend.core.practice.importer import ImportValidationError, parse_practice_bank
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


def test_parser_rejects_non_dp_kfp_case():
    payload = _payload()
    payload["cases"][0]["kind"] = "qcm"
    with pytest.raises(ImportValidationError, match="DP ou KFP"):
        parse_practice_bank(payload)


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
