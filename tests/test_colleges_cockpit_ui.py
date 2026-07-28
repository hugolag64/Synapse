from datetime import date, timedelta
from types import SimpleNamespace

from frontend.pages.colleges_cockpit import _college_item_rows


def _course(course_id, number, title, started=True):
    return SimpleNamespace(
        id=course_id,
        item_number=number,
        title=title,
        date_1ere_lecture=date.today() if started else None,
    )


def _task(course_id, due_date):
    return SimpleNamespace(course_id=course_id, due_date=due_date)


def test_college_item_rows_expose_item_signals_without_extra_queries():
    courses = [_course("c1", "12", "Fragile"), _course("c2", "13", "A lire", started=False)]
    tasks = [_task("c1", date.today() - timedelta(days=1))]

    rows = _college_item_rows(
        courses,
        tasks,
        mastery_by_course={"c1": (24, "critique")},
        urgent_ids={"c1"},
        qcm_map={"c1": {"last_score": 42}},
    )

    assert [row["course"].id for row in rows] == ["c1", "c2"]
    assert rows[0]["level"] == "critique"
    assert rows[0]["urgent"] is True
    assert rows[0]["next_task"] is tasks[0]
    assert rows[0]["qcm_score"] == 42
    assert rows[1]["level"] == "non_commence"
    assert rows[1]["next_task"] is None
    assert rows[1]["qcm_score"] is None


def test_college_item_grid_uses_status_columns_and_readable_empty_state():
    source = open("frontend/pages/colleges_cockpit.py", encoding="utf-8").read()

    for label in ("Progression", "Statut", "Retard", "Fragile", "Prochaine", "QCM"):
        assert f'"{label}"' in source
    assert ".cg-item-status.non-commence" in source
    assert 'ui.label("—").classes("cg-item-cell cg-item-muted cg-item-action")' in source
    assert "aucune révision prévue" not in source
