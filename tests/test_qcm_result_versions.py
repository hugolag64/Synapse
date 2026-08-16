import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    from backend.core.reviews import local_store

    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "qcm-results.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield local_store
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def test_new_qcm_session_creates_initial_snapshot(isolated_db):
    session_id = isolated_db.add_qcm_session_full(
        platform="Synapse IA",
        session_date="2026-08-16",
        item_number="230",
        score_percent=66.67,
        total_questions=3,
        correct_answers=2,
        wrong_answers=1,
        rank_a_questions=2,
        rank_a_correct=1,
    )

    versions = isolated_db.list_qcm_result_versions(session_id)

    assert [(row["phase"], row["revision"]) for row in versions] == [("initial", 1)]
    assert versions[0]["score_percent"] == 66.67
    assert versions[0]["source"] == "live_evaluation"


def test_final_snapshot_is_append_only_and_becomes_current_result(isolated_db):
    session_id = isolated_db.add_qcm_session_full(
        platform="Synapse IA",
        session_date="2026-08-16",
        score_percent=50,
        total_questions=2,
        correct_answers=1,
        wrong_answers=1,
    )

    version_id = isolated_db.record_qcm_result_final(
        session_id,
        source="official_data",
        reason="Rang officiel reçu",
        score_percent=100,
        total_questions=2,
        correct_answers=2,
        wrong_answers=0,
        rank_a_questions=2,
        rank_a_correct=2,
    )

    assert version_id > 0
    versions = isolated_db.list_qcm_result_versions(session_id)
    assert [row["phase"] for row in versions] == ["initial", "final"]
    assert versions[0]["score_percent"] == 50
    assert versions[1]["score_percent"] == 100
    assert isolated_db.get_qcm_sessions_all(limit=1)[0]["score_percent"] == 100


def test_second_final_snapshot_gets_next_revision_and_invalid_input_is_atomic(isolated_db):
    session_id = isolated_db.add_qcm_session_full(
        platform="Synapse IA",
        session_date="2026-08-16",
        score_percent=50,
    )
    isolated_db.record_qcm_result_final(
        session_id,
        source="official_data",
        reason="Première correction",
        score_percent=60,
    )
    isolated_db.record_qcm_result_final(
        session_id,
        source="admin",
        reason="Correction confirmée",
        score_percent=70,
    )

    assert [row["revision"] for row in isolated_db.list_qcm_result_versions(session_id)] == [1, 1, 2]

    with pytest.raises(ValueError):
        isolated_db.record_qcm_result_final(session_id, source="", reason="", score_percent=0)

    assert len(isolated_db.list_qcm_result_versions(session_id)) == 3


def test_final_snapshot_rejects_unknown_session_without_writing(isolated_db):
    with pytest.raises(ValueError, match="introuvable"):
        isolated_db.record_qcm_result_final(
            999,
            source="official_data",
            reason="Correction",
            score_percent=100,
        )
