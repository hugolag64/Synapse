def test_mastery_drift_detects_regression_and_improvement():
    from backend.core.reviews.drift_detector import detect_mastery_drift

    signals = detect_mastery_drift([
        {"course_id": "reg", "week": "2026-W30", "mastery_score": 80},
        {"course_id": "reg", "week": "2026-W31", "mastery_score": 74},
        {"course_id": "reg", "week": "2026-W32", "mastery_score": 68},
        {"course_id": "up", "week": "2026-W30", "mastery_score": 40},
        {"course_id": "up", "week": "2026-W31", "mastery_score": 45},
        {"course_id": "up", "week": "2026-W32", "mastery_score": 50},
    ])

    by_course = {signal.course_id: signal for signal in signals}
    assert by_course["reg"].direction == "regressing"
    assert by_course["reg"].weekly_delta < 0
    assert by_course["up"].direction == "improving"


def test_mastery_drift_requires_minimum_history():
    from backend.core.reviews.drift_detector import detect_mastery_drift

    assert detect_mastery_drift([
        {"course_id": "one", "week": "2026-W32", "mastery_score": 50},
    ]) == []
