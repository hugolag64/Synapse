from pathlib import Path


def test_settings_is_full_width_and_groups_domains_visually():
    source = Path("frontend/pages/settings_cockpit.py").read_text(encoding="utf-8")
    assert ".se-wrap { max-width:none; width:100%;" in source
    assert ".se-domain" in source
    assert "CONNEXIONS" in source
    assert "PLANIFICATION EDN" in source
