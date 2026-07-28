import datetime

from backend.core.knowledge.retention import Evidence, evaluate_retention


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
