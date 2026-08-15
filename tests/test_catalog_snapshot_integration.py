from datetime import date
from types import SimpleNamespace


def test_task_and_history_indexes_are_built_once_per_item():
    from backend.core.reviews.service import (
        build_history_by_course,
        build_review_types_by_course,
        build_tasks_by_item,
    )

    tasks = [
        SimpleNamespace(item_number="255", course_id="fiche-a"),
        SimpleNamespace(item_number="255", course_id="fiche-b"),
        SimpleNamespace(item_number="256", course_id="fiche-c"),
    ]
    history = {
        "task-a": {"course_id": "fiche-a"},
        "task-b": {"course_id": "fiche-b"},
    }

    assert {key: len(value) for key, value in build_tasks_by_item(tasks).items()} == {"255": 2, "256": 1}
    assert build_history_by_course(history)["fiche-a"] == {"task-a"}
    assert build_review_types_by_course({
        "task-a": {"course_id": "fiche-a", "context": "college", "status": "done", "review_type": "J3"},
        "task-b": {"course_id": "fiche-a", "context": "ue", "status": "done", "review_type": "J7"},
    })["fiche-a"] == {"J3"}
