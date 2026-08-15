from datetime import datetime, date

from backend.state.catalog_repository import CatalogItem
from backend.core.notion.models import Cours


class FakeCatalog:
    def __init__(self):
        self.items = [
            CatalogItem("item:1", 1, "Premier", None, None),
            CatalogItem("item:2", 2, "Deuxième", None, None),
            CatalogItem("item:3", 3, "Manquant", None, None),
        ]
        self.fiches = {
            "item:1": ["fiche-1a"],
            "item:2": ["fiche-2a", "fiche-2b"],
            "item:3": [],
        }
        self.colleges = {"item:1": ["Cardiologie"], "item:2": ["Cardiologie", "Pédiatrie"], "item:3": ["Pédiatrie"]}

    def list_items(self):
        return self.items

    def list_fiches(self, item_id):
        return [type("Fiche", (), {"id": fiche_id}) for fiche_id in self.fiches[item_id]]

    def list_colleges_for_item(self, item_id):
        return self.colleges[item_id]


def test_items_has_one_row_per_official_item(monkeypatch):
    from backend.state.store import data_store
    from frontend.pages.items import build_item_rows

    courses = [
        Cours(id="fiche-1a", title="Premier", item_number="1", college=["Cardiologie"], created_time=datetime(2026, 1, 1)),
        Cours(id="fiche-2a", title="Deuxième", item_number="2", college=["Cardiologie"], created_time=datetime(2026, 1, 1)),
        Cours(id="fiche-2b", title="Deuxième", item_number="2", college=["Pédiatrie"], created_time=datetime(2026, 1, 2)),
    ]
    monkeypatch.setattr(data_store, "cours", courses)

    rows = build_item_rows(FakeCatalog())

    assert len(rows) == 3
    assert [row["item_number"] for row in rows] == [1, 2, 3]
    assert rows[1]["colleges"] == ["Cardiologie", "Pédiatrie"]
    assert rows[2]["missing_fiche"] is True


def test_college_global_total_deduplicates_multi_college_items():
    from frontend.pages.colleges_cockpit import build_pilotage_summary

    rows = [
        {"name": "Cardiologie", "item_ids": {"item:1", "item:2"}, "total": 2},
        {"name": "Pédiatrie", "item_ids": {"item:2", "item:3"}, "total": 2},
    ]

    summary = build_pilotage_summary(rows)

    assert summary["total_items"] == 3
    assert summary["total_college_relations"] == 4


def test_college_progress_has_five_levels_and_manual_validation():
    from frontend.components.learning_metrics import college_progress_level

    assert [college_progress_level(value) for value in (0, 10, 50, 80, 100)] == [
        "Non commencé", "En cours", "Parcouru", "Consolidé", "Validé",
    ]
    assert college_progress_level(40, manually_validated=True) == "Validé"
