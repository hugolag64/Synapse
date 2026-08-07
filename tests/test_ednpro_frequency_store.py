import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    from backend.core.reviews import local_store

    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def test_frequency_snapshot_round_trip_and_item_question_filter():
    from backend.core.ednpro import frequency
    from backend.core.reviews import local_store

    rows = frequency.normalize_training_payload(
        [{"item": 221, "priority": "indispensable", "sessions": 4, "questions": 12, "years": [2023, 2025]}],
        source_url="https://ednpro.app/training-v2",
        collected_at="2026-08-04T08:00:00+00:00",
    )
    local_store.replace_ednpro_item_frequencies(rows)

    assert local_store.get_ednpro_item_frequency("221")["years"] == [2023, 2025]
    assert local_store.get_ednpro_frequency_snapshot()["collected_at"] == "2026-08-04T08:00:00+00:00"

    from backend.core.practice.models import PracticeDifficulty, PracticeKind, PracticeSessionSpec
    spec = PracticeSessionSpec(
        practice_kind=PracticeKind.QCM,
        total_questions=2,
        closed_questions=2,
        item_number="221",
        course_id="course-221",
        course_title="Item 221",
        difficulty=PracticeDifficulty.EDN,
    )
    local_store.create_ai_practice_session(
        spec=spec,
        questions=[
            {"kind": "closed", "prompt": "Q1", "choices": ["A", "B"], "answer": "A", "explanation": "ok", "item_numbers": ["221"], "import_metadata": {"source": "EDNpro"}},
            {"kind": "closed", "prompt": "Q2", "choices": ["A", "B"], "answer": "B", "explanation": "ok", "item_numbers": ["222"], "import_metadata": {"source": "EDNpro"}},
        ],
        model="ednpro-import",
    )
    assert [row["prompt"] for row in local_store.get_ednpro_practice_questions("221")] == ["Q1"]


def test_frequency_history_keeps_snapshots_and_reports_changes():
    from backend.core.reviews import local_store

    local_store.replace_ednpro_item_frequencies([
        {
            "item_number": "221", "priority": "important", "session_count": 2,
            "question_count": 8, "years": [2023], "source_url": "training-v2",
            "collected_at": "2026-08-04T08:00:00+00:00",
        },
    ])
    local_store.replace_ednpro_item_frequencies([
        {
            "item_number": "221", "priority": "indispensable", "session_count": 3,
            "question_count": 10, "years": [2023, 2025], "source_url": "training-v2",
            "collected_at": "2027-02-04T08:00:00+00:00",
        },
        {
            "item_number": "330", "priority": "basique", "session_count": 1,
            "question_count": 2, "years": [2026], "source_url": "training-v2",
            "collected_at": "2027-02-04T08:00:00+00:00",
        },
    ])

    history = local_store.get_ednpro_frequency_history()
    changes = local_store.compare_latest_ednpro_frequency_snapshots()

    assert [row["item_count"] for row in history] == [2, 1]
    assert {row["item_number"]: row["status"] for row in changes} == {
        "221": "changed",
        "330": "added",
    }
