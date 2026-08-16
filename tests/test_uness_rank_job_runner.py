from unittest.mock import Mock

import pytest

from backend.core.practice.models import PracticeKind, PracticeSessionSpec
from backend.core.ai.routing import AIModel, AIResponse


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    from backend.core.reviews import local_store

    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "rank-runner.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield local_store
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def _question(store, question_id: str) -> int:
    annale_id = store.create_uness_annale(
        source_url=f"https://uness.example/runner/{question_id}",
        collected_at="2026-08-16T10:00:00+00:00",
        faculte="Faculté test",
        niveau="DFASM1",
        annee=2026,
        matiere="Médecine",
        titre=f"Annale {question_id}",
        type_annale="matiere",
    )
    spec = PracticeSessionSpec(
        practice_kind=PracticeKind.QCM,
        total_questions=1,
        closed_questions=1,
        item_number="233",
        item_numbers=("233",),
    )
    session_id = store.create_ai_practice_session(
        spec=spec,
        questions=[
            {
                "kind": "closed",
                "prompt": f"Énoncé {question_id}",
                "choices": ["A", "B"],
                "answer": '["A"]',
                "explanation": "Correction officielle.",
                "import_metadata": {
                    "uness": {
                        "provenance": {"source": "UNESS"},
                        "question": {
                            "id": question_id,
                            "rank": "",
                            "rank_source": "unknown",
                            "item_numbers": ["233"],
                        },
                    }
                },
                "item_numbers": ("233",),
            }
        ],
        model="uness-verified-local",
    )
    store.set_session_annale_id(session_id, annale_id)
    return session_id


class Course:
    def __init__(self, course_id: str, item_number: str):
        self.id = course_id
        self.item_number = item_number


def test_runner_marks_job_needs_oic_without_calling_gemini(isolated_db, monkeypatch):
    _question(isolated_db, "q-no-oic")
    monkeypatch.setattr(
        "backend.core.reviews.local_store.get_lisa_oic_for_item",
        lambda item_number, course_ids: [],
    )
    service = Mock()

    from backend.core.uness.rank_job_runner import run_uness_rank_cycle

    result = run_uness_rank_cycle(courses=[Course("course-233", "233")], service=service)

    assert result["needs_oic"] == 1
    service.generate.assert_not_called()
    assert isolated_db.list_uness_rank_jobs(status="needs_oic")[0]["last_error"]


def test_runner_calls_gemini_once_per_item_and_applies_confident_rank(isolated_db, monkeypatch):
    _question(isolated_db, "q-a")
    _question(isolated_db, "q-b")
    monkeypatch.setattr(
        "backend.core.reviews.local_store.get_lisa_oic_for_item",
        lambda item_number, course_ids: [
            {"code": "OIC-233-01-A", "intitule": "OIC A", "rang": "A"}
        ],
    )
    service = Mock()
    service.generate.return_value = AIResponse(
        '{"questions":['
        '{"id":"q-a","rank":"A","confidence":0.92,"ambiguous":false,"oic_codes":["OIC-233-01-A"]},'
        '{"id":"q-b","rank":"B","confidence":0.90,"ambiguous":false,"oic_codes":["OIC-233-01-A"]}'
        ']}',
        AIModel.FLASH_LITE,
    )

    from backend.core.uness.rank_job_runner import run_uness_rank_cycle

    result = run_uness_rank_cycle(courses=[Course("course-233", "233")], service=service)

    assert result["resolved"] == 2
    assert service.generate.call_count == 1
    jobs = isolated_db.list_uness_rank_jobs(status="approved")
    assert {job["question_external_id"] for job in jobs} == {"q-a", "q-b"}
    assert {job["gemini_rank"] for job in jobs} == {"A", "B"}


def test_runner_keeps_low_confidence_result_for_admin(isolated_db, monkeypatch):
    _question(isolated_db, "q-uncertain")
    monkeypatch.setattr(
        "backend.core.reviews.local_store.get_lisa_oic_for_item",
        lambda item_number, course_ids: [{"code": "OIC-1", "intitule": "OIC", "rang": "A"}],
    )
    service = Mock()
    service.generate.return_value = AIResponse(
        '{"questions":[{"id":"q-uncertain","rank":"B","confidence":0.71,"ambiguous":true}]}',
        AIModel.FLASH_LITE,
    )

    from backend.core.uness.rank_job_runner import run_uness_rank_cycle

    result = run_uness_rank_cycle(courses=[Course("course-233", "233")], service=service)

    assert result["needs_admin"] == 1
    job = isolated_db.list_uness_rank_jobs(status="needs_admin")[0]
    assert job["gemini_rank"] == ""
    assert job["gemini_raw_response"]


def test_runner_records_retryable_failure_without_blocking_other_jobs(isolated_db, monkeypatch):
    _question(isolated_db, "q-failure")
    monkeypatch.setattr(
        "backend.core.reviews.local_store.get_lisa_oic_for_item",
        lambda item_number, course_ids: [{"code": "OIC-1", "intitule": "OIC", "rang": "A"}],
    )
    service = Mock()
    service.generate.side_effect = RuntimeError("provider unavailable")

    from backend.core.uness.rank_job_runner import run_uness_rank_cycle

    result = run_uness_rank_cycle(courses=[Course("course-233", "233")], service=service)

    assert result["failed"] == 1
    assert isolated_db.list_uness_rank_jobs(status="retry_wait")[0]["last_error"] == "provider unavailable"
