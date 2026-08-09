import datetime

from backend.core.reviews.models import ReviewTask
from backend.core.reviews.recommendation_service import get_next_action


def test_invalid_qcm_score_does_not_trigger_a_qcm_priority():
    task = ReviewTask(
        id="course-1",
        course_id="course-1",
        course_title="Item test",
        theoretical_due_date=datetime.date.today(),
        due_date=datetime.date.today(),
        review_type="J7",
        nb_lectures=3,
        qcm_done=True,
    )

    action = get_next_action(task, last_qcm_score=-5)

    assert action.action_type == "review"
    assert "QCM" not in action.reason
