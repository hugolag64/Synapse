import pytest

from backend.core.reviews import local_store


@pytest.fixture()
def resource_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "resources.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def test_signed_video_url_is_stored_as_stable_page_url(resource_db):
    from backend.core.prep.resources import upsert_prep_resource, list_prep_resources_for_item

    upsert_prep_resource(
        provider="EDNpro",
        resource_type="video",
        title="Athérome",
        url="https://ednpro.app/videos/221?token=secret&expires=123",
        item_number="221",
        confidence=1.0,
    )

    rows = list_prep_resources_for_item("221")

    assert rows[0]["url"] == "https://ednpro.app/videos/221"


def test_item_query_excludes_ambiguous_resources(resource_db):
    from backend.core.prep.resources import upsert_prep_resource, list_prep_resources_for_item

    upsert_prep_resource(
        provider="EDNpro", resource_type="video", title="Sûr",
        url="https://ednpro.app/videos/221", item_number="221", confidence=1.0,
    )
    upsert_prep_resource(
        provider="EDNpro", resource_type="video", title="Ambigu",
        url="https://ednpro.app/videos/other", item_number="221", confidence=0.4,
    )

    rows = list_prep_resources_for_item("221")

    assert [row["title"] for row in rows] == ["Sûr"]
