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

    def list_all_fiches(self):
        return [
            type("Fiche", (), {"id": fiche_id, "item_id": item_id})
            for item_id, fiche_ids in self.fiches.items()
            for fiche_id in fiche_ids
        ]

    def list_colleges_for_item(self, item_id):
        return self.colleges[item_id]

    def list_colleges_by_item(self):
        return dict(self.colleges)


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


def _catalog_row(item_ids: set[str]) -> dict:
    """Ligne minimale au format catalogue attendu par `_pilotage_summary`."""
    return {
        "item_ids": item_ids, "total": len(item_ids), "started": 0, "retard": 0,
        "fragile": 0, "no_pdf": 0, "mastery_by_course": {}, "retention_by_course": {},
        "status_counts": {},
    }


def test_college_global_total_deduplicates_multi_college_items():
    """`build_pilotage_summary` n'était appelée par aucune page — `_compute()`
    construit ses propres lignes et les résume avec `_pilotage_summary` (N21) :
    c'est cette fonction, réellement rendue, qui doit dédupliquer."""
    from frontend.pages.colleges_cockpit import _pilotage_summary

    rows = [
        _catalog_row({"item:1", "item:2"}),
        _catalog_row({"item:2", "item:3"}),
    ]

    summary = _pilotage_summary(rows)

    assert summary["total_courses"] == 3


def test_college_progress_has_five_levels_and_manual_validation():
    from frontend.components.learning_metrics import college_progress_level

    assert [college_progress_level(value) for value in (0, 10, 50, 80, 100)] == [
        "Non commencé", "En cours", "Parcouru", "Consolidé", "Validé",
    ]
    assert college_progress_level(40, manually_validated=True) == "Validé"


def test_realistic_catalog_invariants_are_consistent_across_both_views(monkeypatch):
    from backend.state.store import data_store
    from frontend.pages.colleges_cockpit import _pilotage_summary
    from frontend.pages.items import build_item_rows

    courses = [
        Cours(
            id="fiche-1a",
            title="Premier",
            item_number="1",
            college=["Cardiologie"],
            created_time=datetime(2026, 1, 1),
        ),
        Cours(
            id="fiche-2a",
            title="Deuxième",
            item_number="2",
            college=["Cardiologie"],
            created_time=datetime(2026, 1, 1),
        ),
        Cours(
            id="fiche-2b",
            title="Deuxième",
            item_number="2",
            college=["Pédiatrie"],
            created_time=datetime(2026, 1, 2),
        ),
    ]
    monkeypatch.setattr(data_store, "cours", courses)

    catalog = FakeCatalog()
    item_rows = build_item_rows(catalog)
    college_rows = [
        _catalog_row({"item:1", "item:2"}),
        _catalog_row({"item:2", "item:3"}),
    ]

    assert len(item_rows) == len({row["item_number"] for row in item_rows})
    assert _pilotage_summary(college_rows)["total_courses"] == len(item_rows)
    assert len(item_rows[1]["colleges"]) == 2


# ── Invariants S1 : « commencé » et statut appartiennent à l'item ─────────────


def _item_course(course_id, number, colleges, first_read=None):
    return Cours(
        id=course_id,
        title=f"Item {number}",
        item_number=str(number),
        college=list(colleges),
        date_1ere_lecture=first_read,
        created_time=datetime(2026, 1, 1),
    )


def test_item_status_does_not_depend_on_the_college_it_is_read_from():
    """Un item multi-collèges avait deux statuts : « critique » dans le collège
    validé, « À lire » dans l'autre. 72 items sur 175 étaient concernés."""
    from frontend.pages.colleges_cockpit import _course_semantics

    course = _item_course("fiche-36", 36, ["Endocrinologie", "Gynécologie médicale"])

    depuis_endocrino = _course_semantics(course, 24, "critique", started=True)
    depuis_gyneco = _course_semantics(course, 24, "critique", started=True)

    assert depuis_endocrino["status_key"] == depuis_gyneco["status_key"] == "critique"


def test_a_validated_college_makes_the_item_started_everywhere():
    from backend.core.knowledge.item_progress import is_item_started

    course = _item_course("fiche-36", 36, ["Endocrinologie", "Gynécologie médicale"])

    assert is_item_started(course, validated_colleges={"Endocrinologie"}) is True
    assert is_item_started(course, validated_colleges={"Gynécologie médicale"}) is True
    assert is_item_started(course, validated_colleges=set()) is False


def test_an_item_is_started_by_a_first_read_or_by_any_trace_of_work():
    from backend.core.knowledge.item_progress import is_item_started

    lu = _item_course("fiche-1", 1, ["Cardiologie"], first_read=date(2026, 5, 1))
    travaille = _item_course("fiche-2", 2, ["Cardiologie"])
    intact = _item_course("fiche-3", 3, ["Cardiologie"])

    assert is_item_started(lu) is True
    assert is_item_started(travaille, worked_ids={"fiche-2"}) is True
    assert is_item_started(intact, worked_ids={"fiche-2"}) is False


def test_the_pilotage_panel_counts_the_same_started_items_as_its_own_rows():
    """Le panneau annonçait « 8 / 367 lus » quand ses lignes en comptaient 257."""
    from frontend.pages.colleges_cockpit import _pilotage_summary

    rows = [
        {
            "name": "Cardiologie", "total": 2, "started": 2, "pct": 1.0,
            "retard": 0, "fragile": 0, "no_pdf": 0, "no_pdf_count": 0,
            "item_ids": {"item:1", "item:2"}, "started_item_ids": {"item:1", "item:2"},
            "status_by_item": {"item:1": "fragile", "item:2": "fragile"},
            "mastery_by_course": {}, "retention_by_course": {}, "status_counts": {},
        },
        {
            "name": "Pédiatrie", "total": 2, "started": 1, "pct": 0.5,
            "retard": 0, "fragile": 0, "no_pdf": 0, "no_pdf_count": 0,
            "item_ids": {"item:2", "item:3"}, "started_item_ids": {"item:2"},
            "status_by_item": {"item:2": "fragile", "item:3": "a_lire"},
            "mastery_by_course": {}, "retention_by_course": {}, "status_counts": {},
        },
    ]

    summary = _pilotage_summary(rows)

    # 3 items distincts, 2 commencés : l'item:2 partagé n'est compté qu'une fois
    # et n'est pas perdu parce qu'un autre collège ne l'a pas commencé.
    assert summary["total_courses"] == 3
    assert summary["started"] == 2
    assert sum(summary["status_counts"].values()) == 3


def test_the_pilotage_panel_does_not_double_count_a_fragile_item_across_colleges():
    """`sum(r["fragile"] for r in rows)` comptait un item multi-collèges une
    fois par collège où il apparaît : 246 « fragiles » affichés pour 132 items
    réellement fragiles (N09). Même défaut sur les révisions en retard."""
    from frontend.pages.colleges_cockpit import _pilotage_summary

    rows = [
        {
            "name": "Cardiologie", "total": 2, "started": 2, "pct": 1.0,
            "retard": 1, "fragile": 2, "no_pdf": 0, "no_pdf_count": 0,
            "fragile_item_ids": {"item:1", "item:2"}, "overdue_item_ids": {"item:1"},
            "mastery_by_course": {}, "retention_by_course": {}, "status_counts": {},
        },
        {
            "name": "Pédiatrie", "total": 2, "started": 1, "pct": 0.5,
            "retard": 1, "fragile": 1, "no_pdf": 0, "no_pdf_count": 0,
            "fragile_item_ids": {"item:2"}, "overdue_item_ids": {"item:1"},
            "mastery_by_course": {}, "retention_by_course": {}, "status_counts": {},
        },
    ]

    summary = _pilotage_summary(rows)

    # item:2 est fragile dans les deux collèges, item:1 est en retard dans les
    # deux : chacun ne doit compter qu'une fois au panneau (2 et 1, pas 3 et 2).
    assert summary["fragile"] == 2
    assert summary["overdue"] == 1


def test_the_mastery_snapshot_is_never_unpacked_as_a_pair():
    """`mastery_by_course` porte (score, niveau, preuves). Le lire en deux
    valeurs levait `ValueError: too many values to unpack` et empêchait la page
    Collèges de se construire — sans qu'aucun test ne le voie."""
    from pathlib import Path

    source = Path("frontend/pages/colleges_cockpit.py").read_text(encoding="utf-8")

    assert "score, level = mastery_by_course.get(course.id, (None, None))\n" not in source
    assert "mastery_by_course.get(course.id, (None, None))[:2]" in source


def test_missing_fiche_row_does_not_navigate_to_a_dead_page():
    """Un item sans fiche menait à `/cours/{id}` → « Item introuvable » (N07) ;
    le clic doit informer plutôt que naviguer vers le vide."""
    from pathlib import Path

    source = Path("frontend/pages/items.py").read_text(encoding="utf-8")

    assert "Aucune fiche pour cet item" in source
    assert "it-row-missing" in source
    assert "Fiche manquante" in source


def test_college_rows_tolerate_a_three_valued_mastery_snapshot():
    from frontend.pages.colleges_cockpit import _college_item_rows

    course = _item_course("fiche-1", 1, ["Cardiologie"], first_read=date(2026, 5, 1))

    rows = _college_item_rows(
        [course], [], mastery_by_course={"fiche-1": (58, "fragile", 3)}, started_ids={"fiche-1"}
    )

    assert rows[0]["score"] == 58
    assert rows[0]["level"] == "fragile"
    assert rows[0]["evidence_count"] == 3
