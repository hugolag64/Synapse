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


def test_normalize_training_payload_accepts_ednpro_annales_index_shape():
    from backend.core.ednpro.frequency import normalize_training_payload

    rows = normalize_training_payload(
        [{
            "item_number": 247,
            "nb_sessions": 13,
            "nb_questions": 31,
            "annees": [2025, 2024, 2023, 2022],
        }],
        source_url="https://ednpro.app/training-v2",
        collected_at="2026-08-10T10:27:04+00:00",
    )

    assert rows[0]["priority"] == "indispensable"
    assert rows[0]["session_count"] == 13
    assert rows[0]["question_count"] == 31
    assert rows[0]["years"] == [2022, 2023, 2024, 2025]


def test_priority_without_an_explicit_value_matches_ednpros_own_thresholds():
    """EDNpro affiche sa propre règle sur /training-v2, bloc « Priorité
    d'après les annales » : indispensable à partir de 3 sessions, important à
    2, basique à 1, jamais tombé à 0 (vérifié en direct sur le site le 20 août
    2026). `_priority_from_session_count` la reproduit à l'identique — ce
    n'est pas un seuil local, c'est celui d'EDNpro."""
    from backend.core.ednpro.frequency import normalize_training_payload

    rows = normalize_training_payload(
        [
            {"item_number": 1, "sessions": 3, "questions": 1},
            {"item_number": 2, "sessions": 2, "questions": 1},
            {"item_number": 3, "sessions": 1, "questions": 1},
            {"item_number": 4, "sessions": 0, "questions": 0},
        ],
        source_url="https://ednpro.app/x", collected_at="2026-08-20T00:00:00+00:00",
    )

    priorities = {row["item_number"]: row["priority"] for row in rows}
    assert priorities == {
        "1": "indispensable", "2": "important", "3": "basique", "4": "jamais_tombe",
    }


def test_gain_priority_uses_mastery_gap_and_imported_question_availability():
    from backend.core.ednpro.frequency import calculate_gain_priority

    assert calculate_gain_priority(session_count=5, mastery=20, question_count=10, imported_question_count=5).raw == 200.0
    assert calculate_gain_priority(session_count=5, mastery=80, question_count=10, imported_question_count=5).raw == 50.0
    assert calculate_gain_priority(session_count=5, mastery=20, question_count=10, imported_question_count=0).raw == 0.0


def test_frequency_sync_is_due_after_six_months_or_without_snapshot():
    from backend.core.ednpro.frequency import is_frequency_sync_due

    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    assert is_frequency_sync_due(None, now=now)
    assert not is_frequency_sync_due((now - timedelta(days=179)).isoformat(), now=now)
    assert is_frequency_sync_due((now - timedelta(days=180)).isoformat(), now=now)


def test_gain_priority_separates_unknown_mastery_from_zero_mastery():
    """« Maîtrise inconnue » recevait le même écart maximal que « maîtrise nulle » :
    79 % des items n'ayant aucune mesure, le Top 10 était composé à 100 % d'items
    sur lesquels l'application ne sait rien."""
    from backend.core.ednpro.frequency import calculate_gain_priority

    unknown = calculate_gain_priority(
        session_count=5, mastery=None, question_count=10, imported_question_count=5
    )
    zero = calculate_gain_priority(
        session_count=5, mastery=0, question_count=10, imported_question_count=5
    )

    assert unknown.measured is False
    assert unknown.score is None
    assert zero.measured is True
    assert zero.score is not None


def test_gain_priority_exposes_a_zero_to_hundred_scale():
    """Le nombre brut allait de 0 à 1300 sans échelle affichée."""
    from backend.core.ednpro.frequency import calculate_gain_priority

    top = calculate_gain_priority(
        session_count=13, mastery=0, question_count=10, imported_question_count=10,
        reference_session_count=13,
    )
    half = calculate_gain_priority(
        session_count=13, mastery=50, question_count=10, imported_question_count=10,
        reference_session_count=13,
    )

    assert top.score == 100.0
    assert half.score == 50.0


def test_gain_priority_keeps_its_raw_components_for_the_legend():
    from backend.core.ednpro.frequency import calculate_gain_priority

    result = calculate_gain_priority(
        session_count=5, mastery=20, question_count=10, imported_question_count=5,
        reference_session_count=13,
    )

    assert result.frequency == 5
    assert result.availability == 0.5
    assert result.raw == 200.0


def test_gain_priority_is_zero_when_no_question_is_available():
    from backend.core.ednpro.frequency import calculate_gain_priority

    result = calculate_gain_priority(
        session_count=5, mastery=20, question_count=10, imported_question_count=0
    )

    assert result.measured is True
    assert result.score == 0.0
