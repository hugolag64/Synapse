from pathlib import Path

TODAY = Path("frontend/pages/dashboard/_cockpit_today.py").read_text(encoding="utf-8")


def test_today_mobile_breakpoint_aligns_with_shell():
    assert "@media (max-width: 767.98px)" in TODAY


def test_today_mobile_hides_secondary_queue_headers():
    assert ".ct-qh-dur, .ct-qh-due { display:none; }" in TODAY
