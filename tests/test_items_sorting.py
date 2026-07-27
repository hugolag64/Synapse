from types import SimpleNamespace

from frontend.pages.items import _sort_item_rows


def _row(item, title, colleges):
    return {"course": SimpleNamespace(item_number=item, title=title, college=colleges)}


def test_items_can_be_sorted_by_college_without_duplicate_rows():
    rows = [
        _row("2", "Deux", ["Pneumologie", "Cardiologie"]),
        _row("1", "Un", ["Cardiologie"]),
    ]

    sorted_rows = _sort_item_rows(rows, "college")

    assert [r["course"].title for r in sorted_rows] == ["Un", "Deux"]
    assert len(sorted_rows) == 2


def test_item_sort_keeps_numeric_item_order():
    rows = [_row("10", "Dix", ["A"]), _row("2", "Deux", ["A"])]

    assert [r["course"].title for r in _sort_item_rows(rows, "item")] == ["Deux", "Dix"]
