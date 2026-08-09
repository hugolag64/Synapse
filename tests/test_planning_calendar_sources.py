import pytest

from backend.core.planning.calendar_sources import (
    add_calendar_source,
    list_calendar_sources,
    remove_calendar_source,
)


def test_list_calendar_sources_returns_empty_list_by_default():
    assert list_calendar_sources({}) == []


def test_list_calendar_sources_ignores_malformed_preference():
    assert list_calendar_sources({"planning_calendar_sources": "not-a-list"}) == []
    assert list_calendar_sources({"planning_calendar_sources": [{"label": "Fac"}]}) == []
    assert list_calendar_sources({"planning_calendar_sources": ["not-a-dict"]}) == []


def test_list_calendar_sources_normalizes_entries():
    prefs = {"planning_calendar_sources": [{"id": " abc@x.com ", "label": " Fac "}]}
    assert list_calendar_sources(prefs) == [{"id": "abc@x.com", "label": "Fac"}]


def test_list_calendar_sources_defaults_missing_label_to_empty_string():
    prefs = {"planning_calendar_sources": [{"id": "abc@x.com"}]}
    assert list_calendar_sources(prefs) == [{"id": "abc@x.com", "label": ""}]


def test_add_calendar_source_appends_new_entry():
    result = add_calendar_source([], "abc@x.com", "Fac")
    assert result == [{"id": "abc@x.com", "label": "Fac"}]


def test_add_calendar_source_strips_id_and_label():
    result = add_calendar_source([], "  abc@x.com  ", "  Fac  ")
    assert result == [{"id": "abc@x.com", "label": "Fac"}]


def test_add_calendar_source_rejects_blank_id():
    with pytest.raises(ValueError):
        add_calendar_source([], "   ", "Fac")


def test_add_calendar_source_replaces_existing_entry_without_duplicating():
    existing = [{"id": "abc@x.com", "label": "Fac"}]
    result = add_calendar_source(existing, "abc@x.com", "Faculté de médecine")
    assert result == [{"id": "abc@x.com", "label": "Faculté de médecine"}]


def test_add_calendar_source_accepts_empty_label():
    result = add_calendar_source([], "abc@x.com", "")
    assert result == [{"id": "abc@x.com", "label": ""}]


def test_remove_calendar_source_drops_matching_id():
    existing = [{"id": "abc@x.com", "label": "Fac"}, {"id": "def@x.com", "label": ""}]
    result = remove_calendar_source(existing, "abc@x.com")
    assert result == [{"id": "def@x.com", "label": ""}]


def test_remove_calendar_source_is_noop_for_unknown_id():
    existing = [{"id": "abc@x.com", "label": "Fac"}]
    assert remove_calendar_source(existing, "unknown@x.com") == existing
