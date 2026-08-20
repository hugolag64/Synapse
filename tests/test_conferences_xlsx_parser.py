import datetime

import pytest

from tests.conferences_xlsx_fixtures import write_minimal_xlsx
from backend.core.conferences.xlsx_parser import parse_calendar_xlsx


def test_parses_tuesday_and_thursday_conferences_with_correct_dates(tmp_path):
    rows = {
        2: {1: "2026"},
        3: {1: "Août"},
        4: {1: "1", 2: "Sa"},
        5: {1: "4", 2: "Ma", 3: "HGE"},
        6: {1: "6", 2: "Je", 3: "Onco"},
    }
    path = tmp_path / "calendrier.xlsx"
    write_minimal_xlsx(path, rows)

    conferences = parse_calendar_xlsx(path)

    assert [(c.date, c.weekday_abbr, c.theme_raw) for c in conferences] == [
        (datetime.date(2026, 8, 4), "Ma", "HGE"),
        (datetime.date(2026, 8, 6), "Je", "Onco"),
    ]


def test_resolves_speaker_initials_via_legend(tmp_path):
    rows = {
        2: {1: "2026"},
        3: {1: "Août"},
        4: {1: "1", 2: "Ma", 3: "Onco JFD"},
        10: {1: "JFD", 2: "Jean-François Delattre"},
    }
    path = tmp_path / "calendrier.xlsx"
    write_minimal_xlsx(path, rows)

    conferences = parse_calendar_xlsx(path)

    assert conferences[0].theme_raw == "Onco"
    assert conferences[0].speaker_initials == "JFD"
    assert conferences[0].speaker_name == "Jean-François Delattre"


def test_keeps_theme_whole_when_legend_absent(tmp_path):
    rows = {
        2: {1: "2026"},
        3: {1: "Août"},
        4: {1: "1", 2: "Ma", 3: "Onco JFD"},
    }
    path = tmp_path / "calendrier.xlsx"
    write_minimal_xlsx(path, rows)

    conferences = parse_calendar_xlsx(path)

    assert conferences[0].theme_raw == "Onco JFD"
    assert conferences[0].speaker_initials == ""


def test_stops_a_month_block_at_the_first_non_incrementing_day(tmp_path):
    rows = {
        2: {1: "2026"},
        3: {1: "Août"},
        4: {1: "1", 2: "Ma", 3: "HGE"},
        5: {1: "2", 2: "Me", 3: ""},
        6: {1: "1", 2: "Ma", 3: "Rentrée bis"},
    }
    path = tmp_path / "calendrier.xlsx"
    write_minimal_xlsx(path, rows)

    conferences = parse_calendar_xlsx(path)

    assert [c.theme_raw for c in conferences] == ["HGE"]


def test_resolves_year_after_the_year_boundary_column(tmp_path):
    rows = {
        2: {1: "2026", 5: "2027"},
        3: {1: "Décembre", 5: "Janvier"},
        4: {1: "1", 2: "Ma", 3: "MI", 5: "1", 6: "Ve"},
        5: {1: "8", 2: "Ma", 3: "EDN", 5: "8", 6: "Ve"},
    }
    path = tmp_path / "calendrier.xlsx"
    write_minimal_xlsx(path, rows)

    conferences = parse_calendar_xlsx(path)

    assert conferences[0].date == datetime.date(2026, 12, 1)
    assert conferences[1].date == datetime.date(2026, 12, 8)


def test_raises_when_no_month_header_found(tmp_path):
    rows = {2: {1: "2026"}}
    path = tmp_path / "calendrier.xlsx"
    write_minimal_xlsx(path, rows)

    with pytest.raises(ValueError):
        parse_calendar_xlsx(path)
