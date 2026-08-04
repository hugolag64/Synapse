from datetime import datetime, timedelta, timezone


def test_normalize_training_payload_merges_duplicate_items_and_years():
    from backend.core.ednpro.frequency import normalize_training_payload

    rows = normalize_training_payload(
        {
            "items": [
                {"item": "Item 221", "priority": "Important", "sessions": 2, "questions": 8, "years": [2023, 2022]},
                {"item_number": 221, "category": "important", "session_count": 3, "question_count": 10, "years": [2024]},
                {"item": "Item 2", "priority": "Jamais tombé", "sessions": 0, "questions": 0, "years": []},
            ]
        },
        source_url="https://ednpro.app/training-v2",
        collected_at="2026-08-04T08:00:00+00:00",
    )

    assert rows == [
        {
            "item_number": "2",
            "priority": "jamais_tombe",
            "session_count": 0,
            "question_count": 0,
            "years": [],
            "source_url": "https://ednpro.app/training-v2",
            "collected_at": "2026-08-04T08:00:00+00:00",
        },
        {
            "item_number": "221",
            "priority": "important",
            "session_count": 3,
            "question_count": 10,
            "years": [2022, 2023, 2024],
            "source_url": "https://ednpro.app/training-v2",
            "collected_at": "2026-08-04T08:00:00+00:00",
        },
    ]


def test_gain_priority_uses_mastery_gap_and_imported_question_availability():
    from backend.core.ednpro.frequency import calculate_gain_priority

    assert calculate_gain_priority(session_count=5, mastery=20, question_count=10, imported_question_count=5) == 200.0
    assert calculate_gain_priority(session_count=5, mastery=80, question_count=10, imported_question_count=5) == 50.0
    assert calculate_gain_priority(session_count=5, mastery=20, question_count=10, imported_question_count=0) == 0.0


def test_frequency_sync_is_due_after_ninety_days_or_without_snapshot():
    from backend.core.ednpro.frequency import is_frequency_sync_due

    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    assert is_frequency_sync_due(None, now=now)
    assert not is_frequency_sync_due((now - timedelta(days=89)).isoformat(), now=now)
    assert is_frequency_sync_due((now - timedelta(days=90)).isoformat(), now=now)
