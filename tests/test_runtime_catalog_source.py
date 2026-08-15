from __future__ import annotations

from pathlib import Path

from backend.state.catalog_import import CatalogImportService
from backend.state.store import DataStore


def test_data_store_reads_catalog_rows_after_json_source_is_unavailable(tmp_path, monkeypatch):
    db_path = tmp_path / "synapse.sqlite"
    service = CatalogImportService(db_path=db_path)
    preview = service.preview(Path("data_cache.json"))
    service.apply(Path("data_cache.json"), preview.id)

    monkeypatch.setenv("SYNAPSE_CATALOG_DB_PATH", str(db_path))
    store = DataStore()
    store.CACHE_FILE = str(tmp_path / "missing-cache.json")
    store.LEGACY_CACHE_FILE = str(tmp_path / "missing-legacy-cache.json")

    assert store.load_from_disk(force=True)
    assert len(store.cours) == 582
    assert store.get_item_by_number(255).title == "Diabète gestationnel"
    assert store.get_colleges()
