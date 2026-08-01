"""Tests for the uness_correction_failures retry-queue table and its local_store CRUD."""

from __future__ import annotations

import pytest

from backend.core.reviews import local_store


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def test_record_creates_a_pending_entry_with_attempt_1_and_a_near_future_retry() -> None:
    failure_id = local_store.record_uness_correction_failure(
        bridge_folder="UNESS/à_vérifier/session-1",
        quiz_title="SQI1",
        collected_at="2026-08-01T09:00:00+04:00",
        error_message="Extra data: line 42 column 3 (char 900)",
    )

    failure = local_store.get_uness_correction_failure(failure_id)
    assert failure is not None
    assert failure["quiz_title"] == "SQI1"
    assert failure["attempts"] == 1
    assert failure["status"] == "pending"
    assert failure["error_message"] == "Extra data: line 42 column 3 (char 900)"


def test_recording_the_same_quiz_twice_upserts_instead_of_duplicating() -> None:
    """Two failures for the same (quiz_title, collected_at) must stay one row —
    otherwise the banner grows forever for a quiz that keeps failing every cycle."""
    local_store.record_uness_correction_failure(
        bridge_folder="UNESS/à_vérifier/session-1",
        quiz_title="SQI1",
        collected_at="2026-08-01T09:00:00+04:00",
        error_message="première erreur",
    )

    second_id = local_store.record_uness_correction_failure(
        bridge_folder="UNESS/archives/pneumologie",
        quiz_title="SQI1",
        collected_at="2026-08-01T09:00:00+04:00",
        error_message="deuxième erreur",
    )

    failures = local_store.list_pending_uness_correction_failures()
    assert len(failures) == 1
    assert failures[0]["id"] == second_id
    assert failures[0]["attempts"] == 2
    assert failures[0]["error_message"] == "deuxième erreur"
    assert failures[0]["bridge_folder"] == "UNESS/archives/pneumologie"


def test_resolve_marks_matching_pending_entry_as_resolved() -> None:
    local_store.record_uness_correction_failure(
        bridge_folder="UNESS/à_vérifier/session-1",
        quiz_title="SQI1",
        collected_at="2026-08-01T09:00:00+04:00",
        error_message="erreur",
    )

    local_store.resolve_uness_correction_failure("SQI1", "2026-08-01T09:00:00+04:00")

    assert local_store.list_pending_uness_correction_failures() == []


def test_count_pending_reflects_only_unresolved_entries() -> None:
    local_store.record_uness_correction_failure(
        bridge_folder="f", quiz_title="SQI1", collected_at="2026-08-01T09:00:00+04:00", error_message="e",
    )
    local_store.record_uness_correction_failure(
        bridge_folder="f", quiz_title="DP1", collected_at="2026-08-01T09:00:00+04:00", error_message="e",
    )
    assert local_store.count_pending_uness_correction_failures() == 2

    local_store.resolve_uness_correction_failure("DP1", "2026-08-01T09:00:00+04:00")
    assert local_store.count_pending_uness_correction_failures() == 1


def test_reset_attempts_clears_the_counter_and_pulls_next_retry_to_now() -> None:
    failure_id = local_store.record_uness_correction_failure(
        bridge_folder="f", quiz_title="SQI1", collected_at="2026-08-01T09:00:00+04:00", error_message="e",
    )
    local_store.record_uness_correction_failure(
        bridge_folder="f", quiz_title="SQI1", collected_at="2026-08-01T09:00:00+04:00", error_message="e",
    )
    local_store.record_uness_correction_failure(
        bridge_folder="f", quiz_title="SQI1", collected_at="2026-08-01T09:00:00+04:00", error_message="e",
    )
    assert local_store.list_pending_uness_correction_failures(due_only=True) == []  # 3 tentatives épuisées

    local_store.reset_uness_correction_failure_attempts(failure_id)

    due = local_store.list_pending_uness_correction_failures(due_only=True)
    assert len(due) == 1
    assert due[0]["attempts"] == 0


def test_due_only_excludes_entries_whose_next_retry_is_in_the_future() -> None:
    failure_id = local_store.record_uness_correction_failure(
        bridge_folder="f", quiz_title="SQI1", collected_at="2026-08-01T09:00:00+04:00", error_message="e",
    )
    failure = local_store.get_uness_correction_failure(failure_id)
    assert failure is not None
    # 1ère tentative : délai de 30s, donc pas encore "due" juste après l'appel.
    assert local_store.list_pending_uness_correction_failures(due_only=True) == []
