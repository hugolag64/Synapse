from types import SimpleNamespace
from pathlib import Path

from frontend.components.item_search_palette import search_items


def _course(item, title, colleges):
    return SimpleNamespace(item_number=item, display_item_number=item, title=title, college=colleges)


def test_search_items_matches_item_number_title_and_college():
    courses = [
        _course("75", "Addiction au tabac", ["Psychiatrie"]),
        _course("169", "Infections à VIH", ["Infectiologie"]),
    ]

    assert [c.item_number for c in search_items("75", courses)] == ["75"]
    assert [c.item_number for c in search_items("tabac", courses)] == ["75"]
    assert [c.item_number for c in search_items("infectio", courses)] == ["169"]


def test_search_items_empty_query_returns_recent_slice():
    courses = [_course(str(i), f"Cours {i}", ["Médecine"]) for i in range(12)]

    assert search_items("", courses) == courses[:8]


def test_items_page_imports_palette_for_page_level_keybinding():
    source = Path("frontend/pages/items.py").read_text(encoding="utf-8")
    import_line = "from frontend.components.item_search_palette import open_item_search_palette"
    assert source.index(import_line) < source.index("def items_page")
