from datetime import date
from unittest.mock import patch

from backend.core.reviews.service import ReviewService
from tests.test_review_generation import _make_cours


def test_generate_reviews_active_only_filters_pre_resume_tasks():
    service = ReviewService()
    course = _make_cours(days_since_lecture=32)

    with patch("backend.state.store.data_store") as mock_store:
        mock_store.cours = [course]
        mock_store.preferences = {"study_resume_date": "2026-08-20"}
        full = service.generate_reviews(context="college", history={})
        active = service.generate_reviews(context="college", history={}, active_only=True)

    assert len(full) >= len(active)
    assert any(task.due_date < date(2026, 8, 20) for task in full)
    assert all(task.due_date >= date(2026, 8, 20) for task in active)


def test_generate_all_reviews_forwards_active_only():
    service = ReviewService()

    with patch.object(service, "generate_reviews", return_value=[]) as generate:
        service.generate_all_reviews(history={}, active_only=True)

    assert generate.call_count == 2
    assert all(call.kwargs["active_only"] is True for call in generate.call_args_list)
