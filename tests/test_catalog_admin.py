import pytest

from backend.state.catalog_repository import CatalogRepository


@pytest.fixture
def admin_repository(tmp_path):
    repository = CatalogRepository(tmp_path / "catalog.sqlite")
    repository.upsert_college(college_id="college:cardio", name="Cardiologie", source="test")
    repository.upsert_college(college_id="college:pedia", name="Pédiatrie", source="test")
    repository.upsert_item(item_id="item:1", item_number=1, title="Item 1", provenance="test")
    repository.upsert_item(item_id="item:2", item_number=2, title="Item 2", provenance="test")
    repository.upsert_fiche(
        fiche_id="fiche:1", item_id="item:1", external_notion_id="notion:1",
        title="Item 1", payload={"id": "fiche:1", "title": "Item 1"},
    )
    repository.link_fiche_college(fiche_id="fiche:1", college_name="Cardiologie", source="test")
    return repository


def test_manual_override_requires_justification(admin_repository):
    with pytest.raises(ValueError, match="justification"):
        admin_repository.save_override("item:1", "college:cardio", "add", "")


def test_archive_is_reversible(admin_repository):
    admin_repository.archive_item("item:1", "Retrait temporaire")
    assert admin_repository.get_item("item:1").archived_at is not None
    admin_repository.restore_item("item:1", "Restauration")
    assert admin_repository.get_item("item:1").archived_at is None


def test_merge_keeps_the_master_and_moves_fiches(admin_repository):
    admin_repository.upsert_fiche(
        fiche_id="fiche:2", item_id="item:2", external_notion_id="notion:2",
        title="Item 2", payload={"id": "fiche:2", "title": "Item 2"},
    )
    admin_repository.merge_items("item:1", "item:2", "Doublon confirmé")

    assert admin_repository.get_item("item:2").archived_at is not None
    assert {fiche.item_id for fiche in admin_repository.list_fiches("item:1")} == {"item:1"}


def test_local_title_and_alias_are_audited(admin_repository):
    admin_repository.set_local_title("item:1", "Titre personnel", "Clarification locale")
    admin_repository.add_college_alias("college:cardio", "Cardio", "Alias usuel")

    assert admin_repository.get_item("item:1").title == "Titre personnel"
    assert "Cardio" in admin_repository.list_college_aliases("college:cardio")
    assert any(entry["operation"] == "set_title" for entry in admin_repository.list_audit_log())


def test_fiche_archive_is_reversible(admin_repository):
    admin_repository.archive_fiche("fiche:1", "Fiche obsolète")
    assert admin_repository.list_fiches("item:1") == []
    admin_repository.restore_fiche("fiche:1", "Fiche restaurée")
    assert [fiche.id for fiche in admin_repository.list_fiches("item:1")] == ["fiche:1"]
