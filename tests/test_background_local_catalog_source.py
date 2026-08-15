from pathlib import Path


def test_background_does_not_refresh_notion_when_local_catalog_is_populated():
    source = Path("backend/core/background.py").read_text(encoding="utf-8")

    assert "CatalogRepository().is_populated()" in source
    assert "Catalogue SQLite actif" in source
