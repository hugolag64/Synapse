import datetime as dt
from zoneinfo import ZoneInfo

from backend.core.prep.calendar_parser import (
    event_is_cancelled,
    event_start_date,
    extract_item_numbers,
)


def test_extracts_one_item():
    assert extract_item_numbers("UE2.S7 Médecine Légale - Item 13") == ["13"]


def test_extracts_and_deduplicates_multiple_items():
    title = "UE7.S7 Orthopédie - items 363, 362, 334, 365, 363"
    assert extract_item_numbers(title) == ["363", "362", "334", "365"]


def test_extracts_items_separated_by_et():
    assert extract_item_numbers("Cours - Items 13 et 14") == ["13", "14"]


def test_does_not_parse_ue_time_or_room_numbers():
    title = "UE7.S7 Orthopédie - De 07:45 à 09:45 C017"
    assert extract_item_numbers(title) == []


def test_ignores_title_without_explicit_item_keyword():
    assert extract_item_numbers("UE14 LCA - Introduction") == []


def test_event_start_date_uses_local_timezone_for_datetime():
    event = {"start": {"dateTime": "2026-08-28T23:30:00+00:00"}}
    assert event_start_date(event, ZoneInfo("Indian/Mauritius")) == dt.date(2026, 8, 29)


def test_event_start_date_supports_all_day_events_and_invalid_payloads():
    assert event_start_date({"start": {"date": "2026-08-28"}}, ZoneInfo("Europe/Paris")) == dt.date(2026, 8, 28)
    assert event_start_date({}, ZoneInfo("Europe/Paris")) is None
    assert event_start_date({"start": {"dateTime": "not-a-date"}}, ZoneInfo("Europe/Paris")) is None


def test_event_is_cancelled_reads_google_status():
    assert event_is_cancelled({"status": "cancelled"}) is True
    assert event_is_cancelled({"status": "confirmed"}) is False
