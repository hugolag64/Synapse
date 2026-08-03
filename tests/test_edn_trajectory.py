import datetime
from types import SimpleNamespace


def test_progress_snapshot_uses_started_items_and_recent_throughput():
    from backend.core.edn.trajectory import build_progress_snapshot

    as_of = datetime.date(2026, 8, 3)
    courses = [
        SimpleNamespace(id="1", date_1ere_lecture="2026-08-01"),
        SimpleNamespace(id="2", date_1ere_lecture=None),
        SimpleNamespace(id="3", date_1ere_lecture="2026-07-01"),
    ]
    tasks = [SimpleNamespace(mastery_score=60, days_overdue=2), SimpleNamespace(mastery_score=80, days_overdue=0)]
    history = {
        "a": {"status": "done", "course_id": "1", "completed_at": "2026-08-02T10:00:00", "duration_minutes": 30},
        "b": {"status": "done", "course_id": "3", "completed_at": "2026-07-01T10:00:00", "duration_minutes": 20},
    }

    snapshot = build_progress_snapshot(courses=courses, tasks=tasks, history=history, as_of=as_of)

    assert snapshot.covered_items == 2
    assert snapshot.total_items == 3
    assert snapshot.average_mastery == 70
    assert snapshot.overdue_reviews == 1
    assert snapshot.recent_items_per_week == 0.25


def test_projection_returns_prudent_central_and_ambitious_scenarios():
    from backend.core.edn.trajectory import ProgressSnapshot, project_to_exam

    snapshot = ProgressSnapshot(2, 10, 50, 1, 8, 2.0, 30.0)
    result = project_to_exam(
        snapshot,
        target_date=datetime.date(2026, 9, 2),
        daily_capacity_minutes=60,
    )

    assert [scenario.name for scenario in result] == ["prudent", "central", "ambitieux"]
    assert result[0].projected_coverage <= result[1].projected_coverage <= result[2].projected_coverage
    assert all(0 <= scenario.projected_coverage <= 100 for scenario in result)


def test_sprint_status_exposes_progress_snapshot():
    from backend.core.edn.trajectory import ProgressSnapshot
    from backend.core.planning.sprint_countdown import SprintCountdownService

    snapshot = ProgressSnapshot(2, 10, 50, 1, 8, 0.25, 1.0)
    status = SprintCountdownService("2026-10-15").get_sprint_status(
        today=datetime.date(2026, 8, 3), progress=snapshot
    )

    assert status.covered_items == 2
    assert status.total_items == 10
    assert status.overdue_reviews == 1
    assert status.remaining_reviews == 8
