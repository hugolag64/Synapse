from types import SimpleNamespace

from backend.core.planning.service import planning_service


def test_plan_day_marks_consolidation_slots_distinctly():
    task = SimpleNamespace(
        course_id="course-169",
        item_number="169",
        course_title="Cours à consolider",
        best_pdf_url=None,
        days_overdue=0,
        priority_score=10,
        review_type="consolidation",
        anki=False,
        nb_lectures=1,
        qcm_done=True,
        mastery_level="à consolider",
        college=[],
    )

    plan = planning_service.plan_day([], [task], [])

    assert plan.slots[0].slot_type == "consolidation"
    assert plan.slots[0].source_ref == "consolidation"
    assert plan.slots[0].subtitle.startswith("À consolider")
