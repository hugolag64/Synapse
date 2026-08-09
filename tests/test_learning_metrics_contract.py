from datetime import date

from frontend.components.learning_metrics import build_advancement, build_learning_metrics


def test_advancement_is_read_over_total():
    assert build_advancement(12, 20) == {"done": 12, "total": 20, "percent": 60}


def test_validated_college_marks_all_courses_read():
    assert build_advancement(0, 20, college_validated=True) == {
        "done": 20,
        "total": 20,
        "percent": 100,
    }


def test_unknown_total_does_not_become_zero_percent():
    assert build_advancement(None, None) == {"done": None, "total": None, "percent": None}
    assert build_advancement(0, 0) == {"done": 0, "total": 0, "percent": None}


def test_mastery_and_retention_remain_independent():
    metrics = build_learning_metrics(
        done=20,
        total=20,
        mastery_score=None,
        mastery_level=None,
        retention_score=64,
        retention_stability_days=12.5,
        retention_last_evidence=date(2026, 8, 9),
    )
    assert metrics["mastery"] == {"score": None, "level": None}
    assert metrics["retention"] == {
        "score": 64,
        "stability_days": 12.5,
        "last_evidence": date(2026, 8, 9),
    }
