"""Palette de recherche unique — fusion de command_palette et item_search_palette."""
from types import SimpleNamespace
from pathlib import Path

from frontend.components.command_palette import search_items


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


def test_the_duplicate_item_palette_is_gone():
    assert not Path("frontend/components/item_search_palette.py").exists()


def test_palette_shell_uses_synapse_design_tokens():
    """Seule la coquille de la palette est retokenisée ici. Les dialogs qu'elle
    ouvre (lacune pré-remplie, raccourcis de commande) gardent leur style
    Tailwind : ils relèvent du chantier B."""
    source = Path("frontend/components/command_palette.py").read_text(encoding="utf-8")

    assert "var(--bg)" in source
    assert "var(--border)" in source
    assert 'ui.card().classes("cmd-palette' in source
    assert "rounded-2xl" not in source  # ancienne carte Tailwind de la palette


def test_palette_keeps_keyboard_navigation_over_results():
    """La palette Items offrait ↑↓/Entrée ; la palette fusionnée ne doit pas
    régresser sur ce point, le pied de dialog l'annonce."""
    source = Path("frontend/components/command_palette.py").read_text(encoding="utf-8")

    assert '"ArrowDown"' in source
    assert '"ArrowUp"' in source
    assert '"Enter"' in source
    assert "cmd-palette-result selected" in source or '" selected"' in source


def test_single_global_shortcut_is_ctrl_alt_p():
    bindings = Path("frontend/keybindings.py").read_text(encoding="utf-8")

    assert "e.modifiers.ctrl" in bindings
    assert "e.modifiers.alt" in bindings
    # Les anciens raccourcis, jamais câblés, ne doivent pas réapparaître.
    assert "register_item_search_keybinding" not in bindings
    assert 'key in ("k", "/")' not in bindings


def test_shell_wires_the_global_keybinding_and_shows_the_right_badge():
    source = Path("frontend/cockpit_shell.py").read_text(encoding="utf-8")

    assert "register_keybindings()" in source
    assert "Ctrl Alt P" in source
    assert "⌘K" not in source


def test_items_page_no_longer_registers_its_own_palette():
    source = Path("frontend/pages/items.py").read_text(encoding="utf-8")

    assert "item_search_palette" not in source
    assert "register_item_search_keybinding" not in source
