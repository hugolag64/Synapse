import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.core.notion.client import NotionClient


def _client(request):
    client = NotionClient.__new__(NotionClient)
    client.client = SimpleNamespace(request=request)
    return client


def test_query_database_retries_transient_error(monkeypatch):
    request = AsyncMock(side_effect=[TimeoutError("temporary"), {"results": [], "has_more": False}])
    sleep = AsyncMock()
    monkeypatch.setattr("backend.core.notion.client.asyncio.sleep", sleep)

    result = asyncio.run(_client(request).query_database("db"))

    assert result == []
    assert request.await_count == 2
    sleep.assert_awaited_once_with(0.5)


def test_query_database_does_not_retry_non_transient_error(monkeypatch):
    request = AsyncMock(side_effect=ValueError("invalid request"))
    sleep = AsyncMock()
    monkeypatch.setattr("backend.core.notion.client.asyncio.sleep", sleep)

    with pytest.raises(ValueError, match="invalid request"):
        asyncio.run(_client(request).query_database("db"))

    assert request.await_count == 1
    sleep.assert_not_awaited()
