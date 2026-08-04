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
    assert all(row["url"].startswith("https://") for row in rows)


def test_prep_providers_include_future_edni_without_fake_connection(prep_db):
    from backend.core.prep.catalog import list_prep_providers

    providers = {row["name"]: row for row in list_prep_providers()}

    assert set(providers) >= {"EDNpro", "Hypocampus", "EDNi"}
    assert providers["EDNi"]["enabled"] is False
