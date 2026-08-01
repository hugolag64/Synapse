"""Tests unitaires — pdf_import.py (scan multi-dossiers, collège dérivé du dossier)."""
import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.core.pdf_import import _run_import
from backend.core.files import resolve_college_folder


# ── Fixture : DB temporaire isolée (même pattern que les autres tests knowledge) ──

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import backend.core.reviews.local_store as ls
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(ls, "DB_PATH", test_db)
    monkeypatch.setattr(ls, "_DB", None)
    ls.init_db()
    yield
    if ls._DB is not None:
        ls._DB.close()
    monkeypatch.setattr(ls, "_DB", None)


import backend.core.reviews.local_store as local_store


NOTION_COLLEGES = ["Cardiovasculaire ❤️", "Infectiologie 🦠", "Neurologie 🧠"]

VALID_ITEMS = {
    152: {"item": 152, "title": "Endocardite infectieuse"},
    224: {"item": 224, "title": "Hypertension artérielle"},
}


def _make_folder(root, college_folder, subfolder, filenames):
    d = root / college_folder / subfolder
    d.mkdir(parents=True, exist_ok=True)
    for fname in filenames:
        (d / fname).write_bytes(b"%PDF-1.4 fake")
    return d


def _mock_settings(medicine_dir):
    settings = MagicMock()
    settings.medicine_dir = str(medicine_dir)
    settings.notion.cours_db_id = "db-123"
    return settings


def _mock_p():
    P = MagicMock()
    P.COURS_TITLE = "Titre"
    P.COLLEGE = "Collège"
    P.ITEM = "Item"
    P.ITEM_LIE = "Item lié"
    return P


def _run(coro):
    return asyncio.run(coro)


def _base_mocks(medicine_dir):
    notion_client = AsyncMock()
    notion_client.retrieve_database.return_value = {
        "properties": {
            "Collège": {"multi_select": {"options": [{"name": n} for n in NOTION_COLLEGES]}}
        }
    }
    notion_client.create_page = AsyncMock()

    notion_service = AsyncMock()
    notion_service.get_all_items_map.return_value = {}

    return {
        "settings": _mock_settings(medicine_dir),
        "P": _mock_p(),
        "notion_service": notion_service,
        "notion_client": notion_client,
        "local_store": local_store,
        "all_items": lambda: list(VALID_ITEMS.values()),
        "resolve_college_folder": resolve_college_folder,
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_deux_sous_dossiers_item_sont_tous_les_deux_scannes(tmp_path):
    colleges_root = tmp_path / "Collèges"
    _make_folder(colleges_root, "Cardiovasculaire", "ITEMS", ["152 - Endocardite infectieuse.pdf"])
    _make_folder(colleges_root, "Cardiovasculaire", "ITEMS 25", ["224 - HTA.pdf"])

    mocks = _base_mocks(tmp_path)
    result = _run(_run_import([], False, {"created": 0, "existing_skipped": 0, "failed": 0, "total_found": 0}, **mocks))

    assert result["total_found"] == 2
    assert result["created"] == 2
    calls = mocks["notion_client"].create_page.call_args_list
    created_items = {c.kwargs["properties"]["Item"]["number"] for c in calls}
    assert created_items == {152, 224}


def test_item_dans_deux_dossiers_resolus_cree_avec_les_deux_colleges(tmp_path):
    colleges_root = tmp_path / "Collèges"
    _make_folder(colleges_root, "Cardiovasculaire", "ITEMS", ["152 - Endocardite infectieuse.pdf"])
    _make_folder(colleges_root, "Infectiologie - Pilly", "ITEMS", ["152 - Endocardite infectieuse.pdf"])

    mocks = _base_mocks(tmp_path)
    result = _run(_run_import([], False, {"created": 0, "existing_skipped": 0, "failed": 0, "total_found": 0}, **mocks))

    assert result["created"] == 1
    call = mocks["notion_client"].create_page.call_args_list[0]
    colleges_written = {c["name"] for c in call.kwargs["properties"]["Collège"]["multi_select"]}
    assert colleges_written == {"Cardiovasculaire ❤️", "Infectiologie 🦠"}


def test_item_deja_present_dans_notion_nest_jamais_recree(tmp_path):
    colleges_root = tmp_path / "Collèges"
    _make_folder(colleges_root, "Infectiologie - Pilly", "ITEMS", ["152 - Endocardite infectieuse.pdf"])

    cours_existant = MagicMock()
    cours_existant.item_number = "152"
    cours_existant.college = ["Cardiovasculaire ❤️"]  # collège différent de celui trouvé localement

    mocks = _base_mocks(tmp_path)
    result = _run(_run_import(
        [cours_existant], False,
        {"created": 0, "existing_skipped": 0, "failed": 0, "total_found": 0}, **mocks
    ))

    assert result["created"] == 0
    assert result["existing_skipped"] == 1
    mocks["notion_client"].create_page.assert_not_called()


def test_dossier_non_resolu_est_ignore(tmp_path):
    colleges_root = tmp_path / "Collèges"
    _make_folder(colleges_root, "Anatomie", "ITEMS", ["152 - Endocardite infectieuse.pdf"])

    mocks = _base_mocks(tmp_path)
    result = _run(_run_import([], False, {"created": 0, "existing_skipped": 0, "failed": 0, "total_found": 0}, **mocks))

    assert result["total_found"] == 0
    assert result["created"] == 0
    mocks["notion_client"].create_page.assert_not_called()
