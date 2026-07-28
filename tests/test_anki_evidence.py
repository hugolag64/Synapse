from __future__ import annotations

import datetime

import pytest


@pytest.fixture()
def isolated_anki_db(tmp_path, monkeypatch):
    import backend.core.reviews.local_store as store

    monkeypatch.setattr(store, "DB_PATH", tmp_path / "anki.db")
    monkeypatch.setattr(store, "_DB", None)
    store.init_db()
    yield store
    if store._DB is not None:
        store._DB.close()
    monkeypatch.setattr(store, "_DB", None)


def test_anki_review_is_idempotent(isolated_anki_db):
    store = isolated_anki_db
    when = datetime.datetime(2026, 7, 28, 8, 0, tzinfo=datetime.timezone.utc)

    first = store.record_anki_review(42, 99, ("221",), "good", when, 7, None)
    second = store.record_anki_review(42, 99, ("221",), "good", when, 7, None)

    assert first == second
    assert len(store.get_anki_review_evidence("221")) == 1


def test_multi_item_review_has_one_evidence_per_item(isolated_anki_db):
    store = isolated_anki_db
    when = datetime.datetime(2026, 7, 28, 8, 0, tzinfo=datetime.timezone.utc)

    event_id = store.record_anki_review(42, 99, ("231", "232"), "hard", when, 0, "review-1")

    assert event_id
    assert len(store.get_anki_review_evidence("231")) == 1
    assert len(store.get_anki_review_evidence("232")) == 1
    assert len(store.get_anki_review_evidence()) == 2


def test_different_ratings_are_distinct_events(isolated_anki_db):
    store = isolated_anki_db
    when = datetime.datetime(2026, 7, 28, 8, 0, tzinfo=datetime.timezone.utc)

    store.record_anki_review(42, 99, ("221",), "again", when, 0, None)
    store.record_anki_review(42, 99, ("221",), "good", when, 0, None)

    assert len(store.get_anki_review_evidence("221")) == 2
