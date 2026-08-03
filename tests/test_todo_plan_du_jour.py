"""Tests du résumé de la file de révisions du cockpit Suivi quotidien."""
import datetime
from types import SimpleNamespace

from frontend.pages.todo_cockpit import _revision_summary


def _task(review_type: str, due_date: datetime.date):
    return SimpleNamespace(review_type=review_type, due_date=due_date)


def test_revision_summary_agrege_retard_aujourdhui_et_a_venir():
    today = datetime.date.today()
    summary = _revision_summary(
        [
            _task("J3", today),
            _task("J7", today + datetime.timedelta(days=2)),
            _task("J14", today + datetime.timedelta(days=4)),
        ],
        overdue=1,
    )

    assert summary["overdue"] == 1
    assert summary["today"] == 1
    assert summary["upcoming"] == 2
    assert summary["cycle_counts"] == {"J3": 1, "J7": 1, "J14": 1, "J30": 0}
    assert summary["estimated_minutes"] == 60
