import datetime

from backend.core.edn.trajectory import build_progress_snapshot


def test_projection_ignores_a_malformed_completion_date():
    snapshot = build_progress_snapshot(
        tasks=[],
        history={
            "valid": {
                "status": "done",
                "item_number": "221",
                "completed_at": "2026-08-02T10:00:00",
            },
            "invalid": {
                "status": "done",
                "item_number": "340",
                "completed_at": "not-a-date",
            },
        },
        as_of=datetime.date(2026, 8, 3),
        study_sessions=[{"session_date": "2026-08-02", "duration_minutes": 30}],
        total_edn_items=367,
    )

    assert snapshot.new_items_per_week == 0.25
    assert snapshot.recent_minutes_per_day == round(30 / 28, 2)
