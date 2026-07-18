"""Tests unitaires — adaptateur weak_point -> ReviewTask."""
import datetime
from unittest.mock import MagicMock, patch

from backend.core.notion.models import Cours


def _mock_cours(id, title, college):
    c = MagicMock(spec=Cours)
    c.id = id
    c.title = title
    c.college = college
    return c


def _mock_wp_row(id=1, course_id="course-1", course_title="Cours test",
                  item_number="42", detail="Confusion IRM/TDM avant PL"):
    return {
        "id": id,
        "course_id": course_id,
        "course_title": course_title,
        "item_number": item_number,
        "category": "Examens",
        "detail": detail,
        "severity": 3,
        "status": "active",
        "source_session_id": None,
        "created_at": "2026-07-18T10:00:00",
        "resolved_at": None,
    }


@patch('backend.state.store.data_store')
def test_weak_point_to_task_cours_trouve(mock_data_store):
    from backend.core.reviews.lacune_adapter import weak_point_to_task

    mock_data_store.cours = [_mock_cours("course-1", "Cours test", ["Neurologie 🧠"])]
    row = _mock_wp_row()

    task = weak_point_to_task(row)

    assert task.id == "lacune_1"
    assert task.course_id == "course-1"
    # course_title is set to the lacune's own text (row["detail"]), not the
    # course's title — the card's headline should be "what's wrong", not
    # the course name (see ReviewTask.label = f"ITEM {item_number} – {course_title}").
    assert task.course_title == "Confusion IRM/TDM avant PL"
    assert task.item_number == "42"
    assert task.college == ["Neurologie 🧠"]
    assert task.context == "college"
    assert task.review_type == "lacune"
    assert task.label == "ITEM 42 – Confusion IRM/TDM avant PL"
    assert task.theoretical_due_date == datetime.date.today()
    assert task.due_date == datetime.date.today()


@patch('backend.state.store.data_store')
def test_weak_point_to_task_cours_introuvable(mock_data_store):
    from backend.core.reviews.lacune_adapter import weak_point_to_task

    mock_data_store.cours = []  # course_id ne matche aucun cours chargé
    row = _mock_wp_row(id=2, course_id="orphan-course")

    task = weak_point_to_task(row)

    assert task.id == "lacune_2"
    assert task.college == []
    assert task.context == "college"
    assert task.course_id == "orphan-course"
