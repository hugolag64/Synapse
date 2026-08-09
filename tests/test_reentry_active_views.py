from pathlib import Path


ACTIVE_REVIEW_CALLERS = (
    "frontend/pages/dashboard/_cockpit_today.py",
    "frontend/pages/dashboard/_monday.py",
    "frontend/pages/todo_cockpit.py",
    "frontend/pages/planning_cockpit.py",
    "frontend/pages/colleges_cockpit.py",
    "frontend/pages/items.py",
    "frontend/cockpit_shell.py",
    "backend/features/daily_routine.py",
)


def test_active_views_request_the_central_reentry_filter():
    for path in ACTIVE_REVIEW_CALLERS:
        source = Path(path).read_text(encoding="utf-8")
        assert "active_only=True" in source, path


def test_item_detail_keeps_full_review_generation_for_manual_access():
    source = Path("frontend/pages/course_detail_cockpit.py").read_text(encoding="utf-8")
    assert "active_only=True" not in source


def test_consolidation_reads_the_reentry_boundary():
    source = Path("backend/core/reviews/consolidation.py").read_text(encoding="utf-8")
    assert "filter_active_review_tasks" in source
    assert "get_study_resume_date" in source
