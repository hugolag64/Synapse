from pathlib import Path


TODAY = Path("frontend/pages/dashboard/_cockpit_today.py").read_text(encoding="utf-8")


def test_today_uses_shared_responsive_drawer_contract():
    assert "responsive_drawer" in TODAY
    assert "synapse-responsive-drawer" in TODAY


def test_today_keeps_context_close_callback():
    assert "on_close=" in TODAY
