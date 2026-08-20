"""Traces d'apprentissage rattachées à une fiche absente du catalogue."""

from datetime import datetime

import pytest

from backend.core.notion.models import Cours
from backend.core.reviews import local_store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "integrity.sqlite3"
    monkeypatch.setattr(local_store, "DB_PATH", db_path)
    local_store._DB = None
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    local_store._DB = None


def _course(course_id, number, title):
    return Cours(
        id=course_id, title=title, item_number=str(number),
        college=["Médecine générale 🩺"], created_time=datetime(2026, 1, 1),
    )


def _record(task_id, course_id, item_number, review_type="J3", status="done"):
    with local_store._conn() as con:
        con.execute(
            """INSERT INTO review_history
               (task_id, course_id, course_title, item_number, context, review_type,
                theoretical_due_date, effective_due_date, status, created_at, updated_at)
               VALUES (?, ?, 'Grippe', ?, 'college', ?, '2025-10-05', '2025-10-05', ?, '', '')""",
            (task_id, course_id, str(item_number), review_type, status),
        )


def test_evidence_from_a_vanished_fiche_is_returned_to_its_item(monkeypatch):
    from backend.state.store import data_store
    from backend.state.catalog_integrity import orphan_report, reattach_orphan_evidence

    monkeypatch.setattr(data_store, "cours", [_course("fiche-active", 166, "Grippe")])
    _record("fiche-morte_college_J3_2025-10-05", "fiche-morte", 166)

    assert orphan_report().total_reattachable == 1

    result = reattach_orphan_evidence(apply=True)

    assert result["total_moved"] == 1
    assert orphan_report().is_clean
    with local_store._conn() as con:
        row = con.execute("SELECT course_id, task_id FROM review_history").fetchone()
    # Le task_id encode le course_id : sans réécriture, le moteur reproposerait
    # une révision déjà faite.
    assert row["course_id"] == "fiche-active"
    assert row["task_id"] == "fiche-active_college_J3_2025-10-05"


def test_a_simulation_writes_nothing(monkeypatch):
    from backend.state.store import data_store
    from backend.state.catalog_integrity import reattach_orphan_evidence

    monkeypatch.setattr(data_store, "cours", [_course("fiche-active", 166, "Grippe")])
    _record("fiche-morte_college_J3_2025-10-05", "fiche-morte", 166)

    result = reattach_orphan_evidence(apply=False)

    assert result["total_moved"] == 1 and result["applied"] is False
    with local_store._conn() as con:
        assert con.execute("SELECT course_id FROM review_history").fetchone()[0] == "fiche-morte"


def test_a_review_already_recorded_on_the_target_is_a_duplicate_not_a_loss(monkeypatch):
    from backend.state.store import data_store
    from backend.state.catalog_integrity import orphan_report, reattach_orphan_evidence

    monkeypatch.setattr(data_store, "cours", [_course("fiche-active", 166, "Grippe")])
    _record("fiche-active_college_J3_2025-10-05", "fiche-active", 166)
    _record("fiche-morte_college_J3_2025-10-05", "fiche-morte", 166)

    report = orphan_report()
    assert report.total_duplicates == 1 and report.total_reattachable == 0

    result = reattach_orphan_evidence(apply=True)

    assert result["total_moved"] == 0
    assert result["conflicts"]["review_history"] == 1
    with local_store._conn() as con:
        kept = con.execute(
            "SELECT course_id FROM review_history WHERE task_id LIKE 'fiche-morte%'"
        ).fetchone()
    assert kept["course_id"] == "fiche-morte"  # jamais écrasée, jamais supprimée


def test_leftovers_without_any_item_are_reported_and_never_touched(monkeypatch):
    from backend.state.store import data_store
    from backend.state.catalog_integrity import orphan_report, reattach_orphan_evidence

    monkeypatch.setattr(data_store, "cours", [_course("fiche-active", 166, "Grippe")])
    _record("c1_college_J3_2026-06-22", "c1", "")

    report = orphan_report()
    assert report.total_unknown == 1 and report.unknown_ids == ("c1",)

    assert reattach_orphan_evidence(apply=True)["total_moved"] == 0
    with local_store._conn() as con:
        assert con.execute("SELECT COUNT(*) FROM review_history").fetchone()[0] == 1
