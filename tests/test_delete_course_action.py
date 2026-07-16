"""Tests pour _delete_course_action()"""
import asyncio
from types import SimpleNamespace
from unittest.mock import patch, Mock, MagicMock, AsyncMock
from frontend.components.course_quick_actions import _delete_course_action


def _make_course(id_="c1", college=None):
    return SimpleNamespace(id=id_, title="Splénomégalie", college=college or ["Hématologie"])


def _run(coro):
    """Exécute une coroutine de manière synchrone pour les tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestDeleteCourseAction:
    def test_archives_notion_then_removes_locally_on_success(self):
        course = _make_course()
        refresh_fn = Mock()
        fake_client = MagicMock()
        with patch(
            "frontend.components.course_quick_actions.notion_client.archive_page",
            new_callable=AsyncMock,
        ) as mock_archive, patch(
            "frontend.components.course_quick_actions.data_store.remove_cours",
            new_callable=AsyncMock,
        ) as mock_remove, patch(
            "frontend.components.course_quick_actions.ui.notify"
        ) as mock_notify:
            _run(_delete_course_action(course, refresh_fn, client=fake_client))

        mock_archive.assert_awaited_once_with("c1")
        mock_remove.assert_awaited_once_with("c1")
        refresh_fn.assert_called_once()
        assert mock_notify.call_args.kwargs.get("type") == "warning"

    def test_does_not_touch_local_store_if_notion_archive_fails(self):
        course = _make_course()
        refresh_fn = Mock()
        fake_client = MagicMock()
        with patch(
            "frontend.components.course_quick_actions.notion_client.archive_page",
            new_callable=AsyncMock,
            side_effect=Exception("Notion API error"),
        ), patch(
            "frontend.components.course_quick_actions.data_store.remove_cours",
            new_callable=AsyncMock,
        ) as mock_remove, patch(
            "frontend.components.course_quick_actions.ui.notify"
        ) as mock_notify:
            _run(_delete_course_action(course, refresh_fn, client=fake_client))

        mock_remove.assert_not_called()
        refresh_fn.assert_not_called()
        assert mock_notify.call_args.kwargs.get("type") == "negative"
