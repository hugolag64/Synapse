from unittest.mock import patch

from backend.core.ai_qcm.lacunes import LacuneCandidate, create_lacune


def test_recurrent_lacune_reuses_existing_anchor_instead_of_creating_duplicate():
    candidate = LacuneCandidate(
        detail="Confusion entre les deux examens",
        category="raisonnement",
        severity=4,
        severity_original=3,
        course_id="course-1",
        course_title="Item test",
        item_number="42",
        session_id=12,
        is_recurrence=True,
        existing_wp_id=7,
    )

    with patch("backend.core.ai_qcm.lacunes.local_store") as store:
        result = create_lacune(candidate, severity=4)

    assert result == 7
    store.increment_recurrence.assert_called_once_with(7)
    store.update_weak_point_severity.assert_called_once_with(7, 4)
    store.add_weak_point_full.assert_not_called()
