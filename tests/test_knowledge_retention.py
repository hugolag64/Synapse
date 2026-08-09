import datetime

from backend.core.knowledge.retention import Evidence, evaluate_retention, project_retention


def test_score_declines_with_age_but_not_to_zero():
    today = datetime.date(2026, 7, 28)
    result = evaluate_retention(
        80,
        [Evidence(today - datetime.timedelta(days=90), "lecture", .5)],
        today,
    )
    assert 25 < result.score < 80


def test_successful_repeated_evidence_creates_more_stability_than_one_reading():
    today = datetime.date(2026, 7, 28)
    one = [Evidence(today - datetime.timedelta(days=60), "lecture", .5)]
    repeated = [
        Evidence(today - datetime.timedelta(days=60), "lecture", .5),
        Evidence(today - datetime.timedelta(days=30), "qcm", .9),
        Evidence(today, "anki", .9),
    ]
    assert evaluate_retention(80, repeated, today).stability_days > evaluate_retention(
        80, one, today
    ).stability_days


def test_low_quality_evidence_reduces_stability():
    today = datetime.date(2026, 7, 28)
    good = [Evidence(today - datetime.timedelta(days=30), "qcm", .9)]
    weak = [Evidence(today - datetime.timedelta(days=30), "qcm", .2)]
    assert evaluate_retention(80, weak, today).stability_days < evaluate_retention(
        80, good, today
    ).stability_days


def test_current_evidence_resets_age():
    today = datetime.date(2026, 7, 28)
    result = evaluate_retention(80, [Evidence(today, "qcm", .9)], today)
    assert result.last_evidence == today
    assert result.score == 80


def test_age_produces_a_real_decline_without_rounding_up():
    today = datetime.date(2026, 7, 28)
    result = evaluate_retention(
        26,
        [Evidence(today - datetime.timedelta(days=1), "manual", 1.0)],
        today,
    )
    assert result.score < 26


def test_unknown_source_raises_value_error():
    today = datetime.date(2026, 7, 28)
    try:
        evaluate_retention(80, [Evidence(today, "mystery", .8)], today)
    except ValueError as exc:
        assert "mystery" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown evidence source")


def test_score_is_bounded_and_stability_is_capped():
    today = datetime.date(2026, 7, 28)
    evidence = [Evidence(today - datetime.timedelta(days=i), "qcm", .9) for i in range(80)]

    result = evaluate_retention(150, evidence, today)

    assert 0 <= result.score <= 100
    assert result.stability_days <= 730


def test_lower_bound_respects_floor_and_never_goes_negative():
    today = datetime.date(2026, 7, 28)
    very_low = evaluate_retention(
        5,
        [Evidence(today - datetime.timedelta(days=365), "manual", .1)],
        today,
    )
    floor_applicable = evaluate_retention(
        40,
        [Evidence(today - datetime.timedelta(days=365), "manual", .1)],
        today,
    )

    assert very_low.score >= 0
    assert floor_applicable.score >= 25


def test_floor_applies_to_current_and_aged_scores_below_the_floor():
    today = datetime.date(2026, 7, 28)

    current = evaluate_retention(5, [Evidence(today, "lecture", .5)], today)
    aged = evaluate_retention(
        5,
        [Evidence(today - datetime.timedelta(days=365), "lecture", .5)],
        today,
    )

    assert current.score == 25
    assert aged.score == 25
    assert project_retention(5, 14, 0) == 25


def test_sm2_confidence_three_is_a_low_quality_success():
    from backend.core.reviews.sm2 import compute_next_interval

    interval, factor = compute_next_interval(
        current_interval_days=14,
        confidence=3,
        repetition=2,
    )

    assert interval > 3
    assert factor > 1.3


def test_retention_spacing_makes_same_day_repetitions_less_informative():
    today = datetime.date(2026, 7, 28)
    same_day = [
        Evidence(today, "qcm", 0.9),
        Evidence(today, "qcm", 0.9),
        Evidence(today, "qcm", 0.9),
    ]
    spaced = [
        Evidence(today - datetime.timedelta(days=60), "qcm", 0.9),
        Evidence(today - datetime.timedelta(days=30), "qcm", 0.9),
        Evidence(today, "qcm", 0.9),
    ]

    assert evaluate_retention(80, spaced, today).stability_days > evaluate_retention(
        80, same_day, today
    ).stability_days
