import asyncio
import datetime

import pytest

from backend.core.notion.service import NotionService


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    from backend.core.reviews import local_store

    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "notion-cache.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def test_streak_count_is_cached_for_the_current_day(monkeypatch):
    calls = []

    async def query_database(*args, **kwargs):
        calls.append(1)
        return []

    service = NotionService()
    monkeypatch.setattr("backend.core.notion.service.notion_client.query_database", query_database)

    assert asyncio.run(service.get_streak_counts()) == 0
    assert asyncio.run(service.get_streak_counts()) == 0
    assert len(calls) == 1


def test_streak_cache_is_invalidated_when_the_day_changes(monkeypatch):
    calls = []

    async def query_database(*args, **kwargs):
        calls.append(1)
        return []

    service = NotionService()
    monkeypatch.setattr("backend.core.notion.service.notion_client.query_database", query_database)

    asyncio.run(service.get_streak_counts())
    service._streak_cache_date = datetime.date.today() - datetime.timedelta(days=1)
    asyncio.run(service.get_streak_counts())

    assert len(calls) == 2
