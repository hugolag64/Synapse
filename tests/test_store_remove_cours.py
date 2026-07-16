"""Tests pour DataStore.remove_cours()"""
import asyncio
from datetime import datetime
from unittest.mock import patch
from backend.state.store import DataStore
from backend.core.notion.models import Cours


def _make_cours(id_: str, title: str, item_number: str = "", college: list = None) -> Cours:
    return Cours(
        id=id_,
        title=title,
        item_number=item_number,
        college=college or [],
        created_time=datetime(2024, 1, 1),
    )


def _run(coro):
    """Exécute une coroutine de manière synchrone pour les tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestRemoveCours:
    def test_removes_matching_course(self):
        store = DataStore()
        store.cours = [
            _make_cours("a", "Splénomégalie", "275", college=["Médecine interne"]),
            _make_cours("b", "Splénomégalie", "275", college=["Hématologie"]),
        ]
        with patch.object(DataStore, "save_to_disk"):
            _run(store.remove_cours("a"))
        ids = {c.id for c in store.cours}
        assert ids == {"b"}

    def test_noop_when_id_not_found(self):
        store = DataStore()
        store.cours = [_make_cours("a", "Dyslipidémies", "223")]
        with patch.object(DataStore, "save_to_disk"):
            _run(store.remove_cours("does-not-exist"))
        ids = {c.id for c in store.cours}
        assert ids == {"a"}

    def test_persists_to_disk(self):
        store = DataStore()
        store.cours = [_make_cours("a", "Dyslipidémies", "223")]
        with patch.object(DataStore, "save_to_disk") as mock_save:
            _run(store.remove_cours("a"))
        mock_save.assert_called_once()
