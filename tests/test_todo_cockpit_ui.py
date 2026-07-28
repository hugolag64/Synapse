import datetime
from types import SimpleNamespace

from frontend.pages.todo_cockpit import _revision_summary


def _task(cycle, due):
    return SimpleNamespace(review_type=cycle, due_date=due)


def test_revision_summary_counts_queue_and_cycles():
    today = datetime.date.today()
    tasks = [_task("J3", today - datetime.timedelta(days=1)), _task("J7", today), _task("J7", today + datetime.timedelta(days=2))]

    summary = _revision_summary(tasks, overdue=1)

    assert summary["overdue"] == 1
    assert summary["today"] == 1
    assert summary["upcoming"] == 1
    assert summary["cycle_counts"] == {"J3": 1, "J7": 2, "J14": 0, "J30": 0}
    assert summary["estimated_minutes"] == 60


def test_revision_page_uses_shared_grid_and_full_width_layout():
    source = open("frontend/pages/todo_cockpit.py", encoding="utf-8").read()

    assert ".rv-head, .rv-row { display:grid;" in source
    assert "grid-template-columns:40px 46px minmax(180px,1fr) 140px 84px 84px" in source
    assert 'classes("rv-layout")' in source
    assert "Pilotage des révisions" in source
