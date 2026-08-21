import datetime
from types import SimpleNamespace


def test_progress_snapshot_uses_worked_items_and_recent_throughput():
    """La couverture compte les items EDN dont une révision a été validée
    (auparavant : les fiches portant une date_1ere_lecture)."""
    from backend.core.edn.trajectory import build_progress_snapshot

    as_of = datetime.date(2026, 8, 3)
    tasks = [SimpleNamespace(mastery_score=60, days_overdue=2), SimpleNamespace(mastery_score=80, days_overdue=0)]
    history = {
        "a": {"status": "done", "item_number": "1", "completed_at": "2026-08-02T10:00:00"},
        "b": {"status": "done", "item_number": "3", "completed_at": "2026-07-01T10:00:00"},
    }
    sessions = [{"session_date": "2026-08-02", "duration_minutes": 30}]

    snapshot = build_progress_snapshot(
        tasks=tasks, history=history, as_of=as_of,
        study_sessions=sessions, total_edn_items=367,
    )

    assert snapshot.covered_items == 2
    assert snapshot.total_items == 367
    assert snapshot.average_mastery == 70
    assert snapshot.overdue_reviews == 1
    assert snapshot.new_items_per_week == 0.25
    assert snapshot.recent_minutes_per_day == round(30 / 28, 2)


def test_projection_returns_prudent_central_and_ambitious_scenarios():
    from backend.core.edn.trajectory import ProgressSnapshot, project_to_exam

    snapshot = ProgressSnapshot(2, 10, 50, 1, 8, 2.0, 30.0)
    result = project_to_exam(
        snapshot,
        target_date=datetime.date(2026, 9, 2),
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
