"""Tests unitaires — agrégation du bloc Plan du jour (To Do)."""
import datetime
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import backend.core.reviews.local_store as ls
    import backend.core.knowledge.store as ks

    test_db = tmp_path / "test.db"
    monkeypatch.setattr(ls, "DB_PATH", test_db)
    monkeypatch.setattr(ls, "_DB", None)
    ls.init_db()
    ks.init_knowledge_tables()
    yield
    if ls._DB is not None:
        ls._DB.close()
    monkeypatch.setattr(ls, "_DB", None)


@patch('backend.core.planning.service.planning_service.plan_consolidation')
@patch('backend.core.reviews.service.review_service.generate_reviews')
def test_gather_plan_du_jour_agrege_les_3_sources(mock_generate, mock_plan_consolidation):
    from frontend.pages.todo import _gather_plan_du_jour
    from backend.core.reviews.models import ReviewTask
    import backend.core.reviews.local_store as ls

    today = datetime.date.today()
    review_task = ReviewTask(
        id="rev-1", course_id="course-1", course_title="Cours révision",
        theoretical_due_date=today, due_date=today, review_type="J3",
    )
    mock_generate.return_value = [review_task]

    consolidation_task = ReviewTask(
        id="cons-1", course_id="course-2", course_title="Cours consolidé",
        theoretical_due_date=today, due_date=today, review_type="consolidation",
    )
    mock_plan_consolidation.return_value = ([consolidation_task], [])

    ls.add_weak_point_full(
        course_id="course-3", detail="Oubli hémocultures avant ATB",
        course_title="Cours lacune", item_number="99",
    )

    items = _gather_plan_du_jour()

    ids = {t.id for t in items}
    assert "rev-1" in ids
    assert "cons-1" in ids
    assert any(t.review_type == "lacune" and t.course_title == "Oubli hémocultures avant ATB" for t in items)
    assert len(items) == 3
