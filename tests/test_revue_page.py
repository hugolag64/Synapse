from pathlib import Path


def test_weekly_focus_is_explained_and_uses_full_width_actionable_panel():
    source = Path("frontend/pages/revue.py").read_text(encoding="utf-8")
    assert "Top des catégories de points faibles actifs sur les 30 derniers jours" in source
    assert ".rh-focus { width:100%; box-sizing:border-box;" in source
    assert "focus=" in source
