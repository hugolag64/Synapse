from types import SimpleNamespace

import pytest

from backend.core.reviews import local_store
from frontend.components.course_quick_actions import record_quick_qcm_result


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "qcm-cockpit.db"
    monkeypatch.setattr(local_store, "DB_PATH", db_path)
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def test_cockpit_qcm_result_uses_common_evaluation_facade():
    course = SimpleNamespace(
        id="course-75", title="Item 75", item_number="75"
    )

    outcome, display = record_quick_qcm_result(course, "EDNpro", "11/20")

    assert display == "11/20"
    assert outcome.source == "qcm"
    assert outcome.recommendation == "review_errors"
    rows = local_store.get_qcm_sessions_all(course_id="course-75")
    assert rows[0]["score_percent"] == 55
    assert rows[0]["score_raw"] == "11/20"
    assert rows[0]["platform"] == "EDNpro"

    with local_store._conn() as con:
        assert con.execute("SELECT COUNT(*) FROM weak_points").fetchone()[0] == 0


def test_cockpit_qcm_result_rejects_invalid_score_before_persistence():
    course = SimpleNamespace(id="course-75", title="Item 75", item_number="75")

    with pytest.raises(ValueError, match="Score QCM invalide"):
        record_quick_qcm_result(course, "EDNpro", "pas un score")

    assert local_store.get_qcm_sessions_all(course_id="course-75") == []
