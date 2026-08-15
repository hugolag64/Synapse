from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_item_detail_uses_targeted_review_and_consolidation_queries():
    source = (ROOT / "frontend/pages/course_detail_cockpit.py").read_text(encoding="utf-8")

    assert "review_service.get_tasks_for_course(course_id" in source
    assert "get_due_consolidation_task_for_course" in source
    assert "plan_consolidation()" not in source
    assert "generate_reviews(\n            context=\"college\", history=" not in source
