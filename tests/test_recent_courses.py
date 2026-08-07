"""Historique de consultation des fiches item alimentant la section « Récents »."""
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Chaque test utilise sa propre DB temporaire."""
    import backend.core.reviews.local_store as ls
    monkeypatch.setattr(ls, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(ls, "_DB", None)
    ls.init_db()
    yield
    if ls._DB is not None:
        ls._DB.close()
    monkeypatch.setattr(ls, "_DB", None)


import backend.core.reviews.local_store as ls


def test_visits_are_returned_most_recent_first():
    ls.record_course_visit("a")
    ls.record_course_visit("b")
    ls.record_course_visit("c")

    assert ls.get_recent_course_ids() == ["c", "b", "a"]


def test_revisiting_a_course_moves_it_up_without_duplicating():
    ls.record_course_visit("a")
    ls.record_course_visit("b")
    ls.record_course_visit("a")

    assert ls.get_recent_course_ids() == ["a", "b"]


def test_limit_caps_the_returned_history():
    for course_id in ("a", "b", "c", "d", "e", "f"):
        ls.record_course_visit(course_id)

    assert len(ls.get_recent_course_ids(limit=5)) == 5


def test_empty_history_returns_an_empty_list():
    assert ls.get_recent_course_ids() == []


# ── Rendu sidebar ─────────────────────────────────────────────────────────────

def test_recent_nav_entries_label_and_route_each_course(monkeypatch):
    from frontend import cockpit_shell

    monkeypatch.setattr(
        "backend.core.reviews.local_store.get_recent_course_ids",
        lambda limit=5: ["c1", "c2"],
    )
    monkeypatch.setattr(
        cockpit_shell.data_store, "cours",
        [
            SimpleNamespace(id="c1", title="Athérome", display_item_number="221", item_number="221"),
            SimpleNamespace(id="c2", title="Prescription", display_item_number="", item_number=""),
        ],
        raising=False,
    )

    assert cockpit_shell._recent_nav_entries() == [
        ("Item 221 · Athérome", "/cours/c1"),
        ("Prescription", "/cours/c2"),
    ]


def test_recent_nav_entries_skip_courses_absent_from_the_store(monkeypatch):
    """Un cours supprimé côté Notion reste dans l'historique local : on l'ignore
    plutôt que de rendre un lien mort."""
    from frontend import cockpit_shell

    monkeypatch.setattr(
        "backend.core.reviews.local_store.get_recent_course_ids",
        lambda limit=5: ["gone", "c1"],
    )
    monkeypatch.setattr(
        cockpit_shell.data_store, "cours",
        [SimpleNamespace(id="c1", title="Athérome", display_item_number="221", item_number="221")],
        raising=False,
    )

    assert cockpit_shell._recent_nav_entries() == [("Item 221 · Athérome", "/cours/c1")]


def test_sidebar_hides_the_recents_group_when_history_is_empty():
    from pathlib import Path

    source = Path("frontend/cockpit_shell.py").read_text(encoding="utf-8")

    assert "if recents:" in source
    assert 'Item 221 · Athérome' not in source
