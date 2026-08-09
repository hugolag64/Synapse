from backend.core.practice.flash_zero_service import build_flash_zero_priority


def test_flash_zero_priority_does_not_let_a_malformed_date_beat_a_recent_signal():
    signals = [
        {"item_number": "340", "occurred_at": "not-a-date"},
        {"item_number": "221", "occurred_at": "2026-08-20"},
    ]

    assert build_flash_zero_priority(signals, today="2026-08-21") == ["221", "340"]
