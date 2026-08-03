"""Tests unitaires de la logique exposée par le cockpit Suivi quotidien."""
import datetime
from types import SimpleNamespace

from frontend.pages.todo_cockpit import _revision_summary, _type_tag


def _task(due_date, review_type="J3"):
    return SimpleNamespace(due_date=due_date, review_type=review_type)


def test_revision_summary_counts_overdue_today_upcoming_and_cycles(monkeypatch):
    today = datetime.date(2026, 8, 3)
    monkeypatch.setattr(datetime, "date", type("FixedDate", (datetime.date,), {
        "today": classmethod(lambda cls: today),
    }))
    tasks = [
        _task(today - datetime.timedelta(days=1), "J3"),
        _task(today, "J7"),
        _task(today + datetime.timedelta(days=2), "J30"),
    ]

    assert _revision_summary(tasks, overdue=1) == {
        "overdue": 1,
        "today": 1,
        "upcoming": 1,
        "cycle_counts": {"J3": 1, "J7": 1, "J14": 0, "J30": 1},
        "estimated_minutes": 60,
    }


def test_type_tag_uses_pdf_when_course_has_one():
    assert _type_tag(SimpleNamespace(url_pdf="https://example.test/a.pdf", url_pdf_ue="")) == "PDF"
    assert _type_tag(SimpleNamespace(url_pdf="", url_pdf_ue="")) == "NOTE"
