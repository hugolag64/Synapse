from types import SimpleNamespace

from frontend.pages.items import _sort_item_rows, group_item_rows, visible_item_rows


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


def _full_row(item, title, colleges, level="maîtrisé", overdue=False):
    return {
        "course": SimpleNamespace(item_number=item, title=title, college=colleges),
        "mastery_level": level,
        "overdue": overdue,
    }


def _filt(**overrides):
    base = {"mode": "all", "college": "Tous", "sort": "item"}
    base.update(overrides)
    return base


def test_visible_rows_apply_the_current_sort_mode():
    rows = [
        _full_row("2", "Deux", ["Pneumologie"]),
        _full_row("1", "Un", ["Cardiologie"]),
    ]

    by_item = visible_item_rows(rows, _filt(sort="item"))
    by_college = visible_item_rows(rows, _filt(sort="college"))

    assert [r["course"].title for r in by_item] == ["Un", "Deux"]
    assert [r["course"].title for r in by_college] == ["Un", "Deux"]


def test_switching_sort_mode_changes_the_rendered_order():
    rows = [
        _full_row("1", "Un", ["Pneumologie"]),
        _full_row("2", "Deux", ["Cardiologie"]),
    ]

    by_item = visible_item_rows(rows, _filt(sort="item"))
    by_college = visible_item_rows(rows, _filt(sort="college"))

    assert [r["course"].title for r in by_item] == ["Un", "Deux"]
    assert [r["course"].title for r in by_college] == ["Deux", "Un"]


def test_visible_rows_filter_on_selected_college():
    rows = [
        _full_row("1", "Un", ["Cardiologie"]),
        _full_row("2", "Deux", ["Pneumologie"]),
    ]

    visible = visible_item_rows(rows, _filt(college="Cardiologie", mode="college"))

    assert [r["course"].title for r in visible] == ["Un"]


def test_visible_rows_filter_on_fragile_and_overdue_modes():
    rows = [
        _full_row("1", "Un", ["A"], level="fragile"),
        _full_row("2", "Deux", ["A"], level="critique"),
        _full_row("3", "Trois", ["A"], level="maîtrisé", overdue=True),
    ]

    fragile = visible_item_rows(rows, _filt(mode="fragile"))
    overdue = visible_item_rows(rows, _filt(mode="overdue"))

    assert [r["course"].title for r in fragile] == ["Un", "Deux"]
    assert [r["course"].title for r in overdue] == ["Trois"]


def test_items_list_is_not_capped_at_a_fixed_width():
    from pathlib import Path

    source = Path("frontend/pages/items.py").read_text(encoding="utf-8")

    assert ".it-wrap { max-width:none;" in source
    assert "max-width:1200px" not in source


def test_college_sort_exposes_visible_groups_without_duplicate_items():
    rows = [
        _full_row("2", "Deux", ["Pneumologie"]),
        _full_row("1", "Un", ["Cardiologie"]),
        _full_row("3", "Trois", ["Cardiologie", "Pneumologie"]),
    ]

    groups = group_item_rows(rows)

    assert [name for name, _ in groups] == ["Cardiologie", "Pneumologie"]
    assert [[r["course"].title for r in group] for _, group in groups] == [
        ["Un", "Trois"],
        ["Deux"],
    ]
    assert sum(len(group) for _, group in groups) == len(rows)
