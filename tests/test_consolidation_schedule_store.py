import datetime

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import backend.core.knowledge.store as ks
    import backend.core.reviews.local_store as ls

    test_db = tmp_path / "test.db"
    monkeypatch.setattr(ls, "DB_PATH", test_db)
    monkeypatch.setattr(ls, "_DB", None)
    ls.init_db()
    ks.init_knowledge_tables()
    yield
    if ls._DB is not None:
        ls._DB.close()
    monkeypatch.setattr(ls, "_DB", None)


import backend.core.reviews.local_store as ls  # noqa: E402


def test_empty_map_when_nothing_stored():
    assert ls.get_consolidation_schedule_map("college") == {}


def test_batch_upsert_then_read_back():
    d1 = datetime.date(2026, 8, 21)
    d2 = datetime.date(2026, 8, 22)
    ls.set_consolidation_schedule_batch("college", {"course-1": d1, "course-2": d2})

    assert ls.get_consolidation_schedule_map("college") == {"course-1": d1, "course-2": d2}


def test_batch_upsert_overwrites_an_existing_date():
    d1 = datetime.date(2026, 8, 21)
    d2 = datetime.date(2026, 8, 25)
    ls.set_consolidation_schedule_batch("college", {"course-1": d1})
    ls.set_consolidation_schedule_batch("college", {"course-1": d2})

    assert ls.get_consolidation_schedule_map("college") == {"course-1": d2}


def test_contexts_are_isolated():
    d = datetime.date(2026, 8, 21)
    ls.set_consolidation_schedule_batch("college", {"course-1": d})
    ls.set_consolidation_schedule_batch("ue", {"course-1": d})

    ls.delete_consolidation_schedule(["course-1"], "ue")

    assert ls.get_consolidation_schedule_map("college") == {"course-1": d}
    assert ls.get_consolidation_schedule_map("ue") == {}


def test_delete_removes_only_the_given_ids():
    d = datetime.date(2026, 8, 21)
    ls.set_consolidation_schedule_batch("college", {"course-1": d, "course-2": d})

    ls.delete_consolidation_schedule(["course-1"], "college")

    assert ls.get_consolidation_schedule_map("college") == {"course-2": d}


def test_clear_from_removes_entries_on_or_after_the_given_date_only():
    ls.set_consolidation_schedule_batch("college", {
        "course-1": datetime.date(2026, 8, 20),
        "course-2": datetime.date(2026, 8, 21),
        "course-3": datetime.date(2026, 8, 22),
    })

    ls.clear_consolidation_schedule_from("college", datetime.date(2026, 8, 21))

    assert ls.get_consolidation_schedule_map("college") == {"course-1": datetime.date(2026, 8, 20)}
