from datetime import datetime

from backend.core.notion.models import Cours


def _make_cours(**kwargs) -> Cours:
    defaults = dict(
        id="test-id",
        title="Pathologie cardiovasculaire",
        item_number=None,
        item_lie=None,
        college=[],
        semestre=None,
        ue_id=None,
        created_time=datetime(2024, 1, 1),
        nb_lectures=0,
    )
    defaults.update(kwargs)
    return Cours(**defaults)


def test_empty_item_number_with_resolvable_item_lie_is_a_correction():
    from scripts.reconcile_item_numbers import find_item_number_corrections

    cours = [_make_cours(id="page-1", title="Méningite", item_number=None, item_lie="item-page-221")]
    page_id_to_item_num = {"item-page-221": 221}

    corrections = find_item_number_corrections(cours, page_id_to_item_num)

    assert corrections == [{"page_id": "page-1", "title": "Méningite", "item_number": 221}]


def test_already_filled_item_number_is_never_a_correction():
    from scripts.reconcile_item_numbers import find_item_number_corrections

    cours = [_make_cours(id="page-1", item_number="221", item_lie="item-page-340")]
    page_id_to_item_num = {"item-page-340": 340}

    assert find_item_number_corrections(cours, page_id_to_item_num) == []


def test_no_item_lie_at_all_is_not_a_correction():
    from scripts.reconcile_item_numbers import find_item_number_corrections

    cours = [_make_cours(id="page-1", item_number=None, item_lie=None)]

    assert find_item_number_corrections(cours, {}) == []


def test_item_lie_pointing_to_unknown_page_is_not_a_correction_and_does_not_raise():
    from scripts.reconcile_item_numbers import find_item_number_corrections

    cours = [_make_cours(id="page-1", item_number=None, item_lie="deleted-page-id")]

    assert find_item_number_corrections(cours, {}) == []
