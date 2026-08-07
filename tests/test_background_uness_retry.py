"""Tests for the bounded auto-retry step of UNESS correction failures in the
background sync loop (backend/core/background.py)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from backend.core import background


def test_retry_pending_uness_corrections_retries_every_due_failure():
    due = [{"id": 1}, {"id": 2}]
    with patch(
        "backend.core.reviews.local_store.list_pending_uness_correction_failures",
        return_value=due,
    ), patch("backend.core.uness.gemini_autocorrect.retry_failed_quiz") as mocked_retry:
        asyncio.run(background._retry_pending_uness_corrections())

    assert mocked_retry.call_count == 2
    mocked_retry.assert_any_call(1)
    mocked_retry.assert_any_call(2)


def test_retry_pending_uness_corrections_does_nothing_when_queue_is_empty():
    with patch(
        "backend.core.reviews.local_store.list_pending_uness_correction_failures",
        return_value=[],
    ), patch("backend.core.uness.gemini_autocorrect.retry_failed_quiz") as mocked_retry:
        asyncio.run(background._retry_pending_uness_corrections())

    mocked_retry.assert_not_called()


def test_retry_pending_uness_corrections_continues_after_one_retry_raises():
    due = [{"id": 1}, {"id": 2}]

    def _side_effect(failure_id):
        if failure_id == 1:
            raise RuntimeError("boom")
        return {"success": True, "error": None}

    with patch(
        "backend.core.reviews.local_store.list_pending_uness_correction_failures",
        return_value=due,
    ), patch(
        "backend.core.uness.gemini_autocorrect.retry_failed_quiz", side_effect=_side_effect
    ) as mocked_retry:
        asyncio.run(background._retry_pending_uness_corrections())

    assert mocked_retry.call_count == 2


def test_retry_pending_notion_sync_replays_and_resolves_success(monkeypatch):
    from backend.core import background
    from backend.core.reviews import local_store

    pending = [{"id": 7, "course_id": "course-1", "properties": {"done": True}}]
    resolved = []
    monkeypatch.setattr(local_store, "list_pending_notion_sync", lambda due_only: pending)
    monkeypatch.setattr(local_store, "resolve_notion_sync", resolved.append)

    async def succeed(*args, **kwargs):
        return True

    monkeypatch.setattr(background.notion_service, "update_course", succeed)

    asyncio.run(background._retry_pending_notion_sync())

    assert resolved == [7]
