import datetime

from backend.core.knowledge.retention import Evidence, evaluate_retention


def test_neutral_evidence_does_not_increase_retention_stability():
    today = datetime.date(2026, 7, 28)
    initial = [Evidence(today - datetime.timedelta(days=60), "lecture", 0.5)]
    with_neutral_qcm = initial + [Evidence(today, "qcm", 0.5)]

    assert evaluate_retention(80, with_neutral_qcm, today).stability_days == evaluate_retention(
        80, initial, today
    ).stability_days
