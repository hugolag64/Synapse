from pathlib import Path


def test_statistics_navigation_uses_explicit_title():
    stats_source = Path("frontend/pages/stats.py").read_text(encoding="utf-8")
    dashboard_source = Path("frontend/pages/dashboard/_dialogs.py").read_text(encoding="utf-8")
    shell_source = Path("frontend/cockpit_shell.py").read_text(encoding="utf-8")

    assert 'with frame("Statistiques")' in stats_source
    assert "Voir mes statistiques" in dashboard_source
    assert '"Statistiques": "Statistiques"' in shell_source


def test_item_surfaces_do_not_use_generic_progression_label_for_learning_metrics():
    items_source = Path("frontend/pages/items.py").read_text(encoding="utf-8")
    detail_source = Path("frontend/pages/course_detail_cockpit.py").read_text(encoding="utf-8")
    stats_source = Path("frontend/pages/stats.py").read_text(encoding="utf-8")

    assert 'ui.label("Progression")' not in items_source
    assert 'ui.label("Progression")' not in detail_source
    assert 'ui.label("Progression des objectifs")' in stats_source
