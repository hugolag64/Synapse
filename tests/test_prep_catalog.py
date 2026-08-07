import pytest

from backend.core.reviews import local_store


@pytest.fixture()
def prep_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "prep.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def test_default_ednpro_shortcuts_are_grouped_by_category(prep_db):
    from backend.core.prep.catalog import list_prep_shortcuts

    rows = list_prep_shortcuts("EDNpro")

    assert {row["category"] for row in rows} >= {"annales", "iconographie", "videos"}
    assert any(row["title"] == "Masterclass" and row["url"] == "https://ednpro.app/masterclass" for row in rows)
    assert all(row["url"].startswith("https://") for row in rows)


def test_prep_providers_include_future_edni_without_fake_connection(prep_db):
    from backend.core.prep.catalog import list_prep_providers

    providers = {row["name"]: row for row in list_prep_providers()}

    assert set(providers) >= {"EDNpro", "Hypocampus", "EDNi"}
    assert providers["EDNi"]["enabled"] is False


def test_list_recent_prep_shortcuts_returns_empty_when_nothing_used(prep_db):
    from backend.core.prep.catalog import list_recent_prep_shortcuts

    assert list_recent_prep_shortcuts() == []


def test_list_recent_prep_shortcuts_only_returns_shortcuts_with_last_used(prep_db):
    from backend.core.prep.catalog import list_prep_shortcuts, record_prep_access, list_recent_prep_shortcuts

    rows = list_prep_shortcuts("EDNpro")
    target = next(r for r in rows if r["title"] == "Masterclass")
    record_prep_access(target["id"])

    recent = list_recent_prep_shortcuts()

    assert len(recent) == 1
    assert recent[0]["title"] == "Masterclass"
    assert recent[0]["last_used"] is not None


def test_list_recent_prep_shortcuts_orders_most_recent_first(prep_db):
    from backend.core.prep.catalog import list_prep_shortcuts, record_prep_access, list_recent_prep_shortcuts

    rows = list_prep_shortcuts("EDNpro")
    first, second = rows[0], rows[1]
    record_prep_access(first["id"])
    record_prep_access(second["id"])

    recent = list_recent_prep_shortcuts()

    assert recent[0]["id"] == second["id"]
    assert recent[1]["id"] == first["id"]


def test_list_recent_prep_shortcuts_respects_limit(prep_db):
    from backend.core.prep.catalog import list_prep_shortcuts, record_prep_access, list_recent_prep_shortcuts

    rows = list_prep_shortcuts("EDNpro")
    for row in rows[:3]:
        record_prep_access(row["id"])

    recent = list_recent_prep_shortcuts(limit=2)

    assert len(recent) == 2
