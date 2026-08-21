from pathlib import Path


def _source() -> str:
    return Path("frontend/pages/planning_cockpit.py").read_text(encoding="utf-8")


def test_load_and_render_uses_the_persisted_schedule():
    source = _source()
    assert "consolidation.ensure_schedule(" in source
    assert 'schedule_map.get(task.course_id) == d' in source


def test_consolidation_fetch_horizon_covers_the_schedule_horizon():
    assert "consolidation.SCHEDULE_HORIZON_DAYS" in _source()
