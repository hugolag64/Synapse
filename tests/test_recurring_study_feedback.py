import json

import pytest

from backend.core.reviews import local_store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "reviews.db"
    monkeypatch.setattr(local_store, "DB_PATH", db_path)
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def test_second_matching_study_feedback_creates_one_pending_gap_proposal():
    for detail in ("Erreur 1", "Erreur 2"):
        local_store.add_study_session(
            "course-1",
            course_title="Cardiologie",
            item_number="75",
            qcm_result="raté",
            weak_category="raisonnement",
            weak_detail=detail,
        )

    proposals = local_store.get_pending_proposals()
    with local_store._conn() as con:
        weak_points = con.execute("SELECT COUNT(*) FROM weak_points").fetchone()[0]

    assert len(proposals) == 1
    assert proposals[0]["item_number"] == "75"
    assert proposals[0]["error_type"] == "raisonnement"
    assert proposals[0]["occurrence_count"] == 2
    assert weak_points == 0


def test_rechecking_matching_study_feedback_keeps_one_tagged_proposal():
    first_session_id = local_store.add_study_session(
        "course-1", item_number="75", weak_category="raisonnement", weak_detail="Erreur 1"
    )
    second_session_id = local_store.add_study_session(
        "course-1", item_number="75", weak_category="raisonnement", weak_detail="Erreur 2"
    )

    local_store.check_and_propose_recurring_study_feedback(
        item_number="75",
        error_type="raisonnement",
        new_session_id=second_session_id,
    )

    proposals = local_store.get_pending_proposals()
    assert len(proposals) == 1
    assert json.loads(proposals[0]["session_ids"]) == [
        f"study:{first_session_id}",
        f"study:{second_session_id}",
    ]
