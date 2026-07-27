from types import SimpleNamespace

from frontend.pages.colleges_cockpit import _college_item_rows


def test_college_item_rows_are_simplified_and_keep_review_task():
    courses = [
        SimpleNamespace(id="c2", title="Deuxième item", item_number="12"),
        SimpleNamespace(id="c1", title="Premier item", item_number="3"),
    ]
    tasks = [SimpleNamespace(course_id="c1", review_type="J7")]

    rows = _college_item_rows(courses, tasks)

    assert [row["course"].id for row in rows] == ["c1", "c2"]
    assert rows[0]["task"].review_type == "J7"
    assert rows[1]["task"] is None
