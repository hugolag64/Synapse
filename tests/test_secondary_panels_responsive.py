from pathlib import Path


def test_revisions_panel_uses_responsive_drawer_contract():
    source = Path("frontend/pages/todo_cockpit.py").read_text(encoding="utf-8")
    assert "responsive_drawer" in source
    assert "synapse-responsive-drawer" in source


def test_colleges_panel_uses_responsive_drawer_contract():
    source = Path("frontend/pages/colleges_cockpit.py").read_text(encoding="utf-8")
    assert "responsive_drawer" in source
    assert "synapse-responsive-drawer" in source
