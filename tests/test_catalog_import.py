from __future__ import annotations

from pathlib import Path

from backend.state.catalog_import import CatalogImportService


def test_preview_import_contains_all_official_items_and_archives_non_item_courses(tmp_path):
    service = CatalogImportService(db_path=tmp_path / "synapse.sqlite")

    preview = service.preview(Path("data_cache.json"))

    assert preview.item_count == 367
    assert preview.fiche_count == 582
    assert preview.archived_course_count == 125
    assert preview.ambiguous_matches == 0


def test_apply_then_rollback_restores_catalog(tmp_path):
    service = CatalogImportService(db_path=tmp_path / "synapse.sqlite")

    preview = service.preview(Path("data_cache.json"))
    run = service.apply(Path("data_cache.json"), preview.id)

    assert service.repository.count_items() == 367
    assert service.repository.count_fiches() == 582
    assert service.repository.count_archived_courses() == 125

    service.rollback(run.id)

    assert service.repository.count_items() == 0
    assert service.repository.count_fiches() == 0
    assert service.repository.count_archived_courses() == 0
