import datetime

from backend.core.edn.trajectory import build_progress_snapshot


def test_projection_ignores_a_malformed_completion_date():
    snapshot = build_progress_snapshot(
        courses=[],
        tasks=[],
        history={
            "valid": {
                "status": "done",
                "course_id": "221",
                "completed_at": "2026-08-02T10:00:00",
                "duration_minutes": 30,
            },
            "invalid": {
                "status": "done",
                "course_id": "340",
                "completed_at": "not-a-date",
                "duration_minutes": 90,
            },
        },
        as_of=datetime.date(2026, 8, 3),
    )

    assert snapshot.recent_items_per_week == 0.25
    assert snapshot.recent_minutes_per_day == round(30 / 28, 2)
