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


def test_priority_without_an_explicit_value_uses_quartiles_on_a_large_batch():
    """Sur données réelles, `session_count >= 3` classait 205 items sur 367
    (56 %) en « indispensable » — un seuil fixe qui ne s'adapte pas au volume
    du corpus. Sur un lot assez grand, seul le quartile supérieur de
    `session_count × question_count` doit porter le badge maximal (Q3)."""
    from backend.core.ednpro.frequency import normalize_training_payload

    # 12 items : 8 avec un score identique et faible (2), 4 avec un score
    # nettement plus élevé (score 132) — seuls ces 4 doivent ressortir
    # « indispensable » ; sous l'ancien seuil fixe (session_count >= 3), les
    # 4 items à score faible mais 3 sessions l'auraient aussi été.
    rows_payload = [
        {"item_number": i, "sessions": 1, "questions": 2} for i in range(1, 9)
    ] + [
        {"item_number": i, "sessions": 11, "questions": 12} for i in range(9, 13)
    ]

    rows = normalize_training_payload(
        rows_payload, source_url="https://ednpro.app/x", collected_at="2026-08-20T00:00:00+00:00",
    )

    priorities = {row["item_number"]: row["priority"] for row in rows}
    assert all(priorities[str(i)] == "indispensable" for i in range(9, 13))
    assert all(priorities[str(i)] != "indispensable" for i in range(1, 9))


def test_priority_falls_back_to_fixed_thresholds_below_the_quartile_minimum():
    """Un lot trop petit pour un quartile statistiquement sensé retombe sur
    les seuils historiques plutôt que de produire un classement arbitraire."""
    from backend.core.ednpro.frequency import normalize_training_payload

    rows = normalize_training_payload(
        [{"item_number": 1, "sessions": 3, "questions": 1}],
        source_url="https://ednpro.app/x", collected_at="2026-08-20T00:00:00+00:00",
    )

    assert rows[0]["priority"] == "indispensable"


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
