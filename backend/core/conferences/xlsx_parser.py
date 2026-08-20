"""Lit un fichier XLS "grille calendrier" (mois en colonnes, jours en lignes) tel
que fourni par la faculté pour le planning des conférences DFASM. Seul le texte
des cellules est exploité — la couleur de remplissage n'est pas lue (v1)."""
from __future__ import annotations

import datetime
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

_MONTHS_FR = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "décembre": 12,
}

_YEAR_RE = re.compile(r"^\d{4}$")
_INITIALS_RE = re.compile(r"^[A-ZÉÈÀ]{2,5}\.?\*?$")


@dataclass(frozen=True)
class ParsedConference:
    date: datetime.date
    weekday_abbr: str
    theme_raw: str
    speaker_initials: str
    speaker_name: str


def parse_calendar_xlsx(path: Path) -> list[ParsedConference]:
    rows = _read_sheet_rows(path)
    legend = _read_legend(rows)

    month_row_num, month_cols = _find_month_header(rows)
    if month_row_num is None:
        raise ValueError("Aucune ligne d'en-tête de mois trouvée dans le classeur.")
    year_row = rows.get(month_row_num - 1, {})
    years_by_col = {
        col: int(str(value).strip())
        for col, value in year_row.items()
        if value and _YEAR_RE.match(str(value).strip())
    }
    if not years_by_col:
        raise ValueError(
            "Impossible de déterminer l'année du calendrier (ligne des années absente)."
        )

    conferences: list[ParsedConference] = []
    for month_col, month_number in month_cols.items():
        year = _year_for_column(month_col, years_by_col)
        previous_day = 0
        row_num = month_row_num + 1
        while True:
            row = rows.get(row_num)
            if row is None:
                break
            day_text = str(row.get(month_col) or "").strip()
            if not day_text.isdigit():
                break
            day = int(day_text)
            if day < previous_day:
                break
            previous_day = day
            weekday_abbr = str(row.get(month_col + 1) or "").strip()
            theme_cell = str(row.get(month_col + 2) or "").strip()
            if theme_cell:
                try:
                    conf_date = datetime.date(year, month_number, day)
                except ValueError:
                    row_num += 1
                    continue
                theme, initials, speaker_name = _split_speaker(theme_cell, legend)
                conferences.append(
                    ParsedConference(
                        date=conf_date,
                        weekday_abbr=weekday_abbr,
                        theme_raw=theme,
                        speaker_initials=initials,
                        speaker_name=speaker_name,
                    )
                )
            row_num += 1
    return conferences


def _split_speaker(theme_cell: str, legend: dict[str, str]) -> tuple[str, str, str]:
    parts = theme_cell.rsplit(" ", 1)
    if len(parts) == 2:
        theme, last = parts
        key = last.strip("*").upper()
        if key in legend:
            return theme.strip(), last.strip(), legend[key]
    return theme_cell, "", ""


def _col_to_index(ref: str) -> int:
    letters = "".join(c for c in ref if c.isalpha())
    idx = 0
    for c in letters:
        idx = idx * 26 + (ord(c.upper()) - ord("A") + 1)
    return idx


def _cell_text(cell: ET.Element, shared: list[str]) -> str | None:
    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        is_el = cell.find("m:is", _NS)
        if is_el is None:
            return None
        texts = is_el.findall(".//m:t", _NS)
        return "".join(t.text or "" for t in texts)
    value_el = cell.find("m:v", _NS)
    if value_el is None:
        return None
    value = value_el.text
    if cell_type == "s" and value is not None:
        return shared[int(value)]
    return value


def _read_sheet_rows(path: Path) -> dict[int, dict[int, str]]:
    with zipfile.ZipFile(path) as archive:
        sheet_xml = archive.read("xl/worksheets/sheet1.xml")
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            sst_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for si in sst_root.findall("m:si", _NS):
                texts = si.findall(".//m:t", _NS)
                shared.append("".join(t.text or "" for t in texts))

    root = ET.fromstring(sheet_xml)
    rows: dict[int, dict[int, str]] = {}
    for row_el in root.findall(".//m:row", _NS):
        row_num = int(row_el.get("r"))
        cells: dict[int, str] = {}
        for cell in row_el.findall("m:c", _NS):
            ref = cell.get("r")
            if not ref:
                continue
            text = _cell_text(cell, shared)
            if text is not None:
                cells[_col_to_index(ref)] = text
        if cells:
            rows[row_num] = cells
    return rows


def _find_month_header(rows: dict[int, dict[int, str]]) -> tuple[int | None, dict[int, int]]:
    for row_num in sorted(rows):
        found: dict[int, int] = {}
        for col, value in rows[row_num].items():
            month_number = _MONTHS_FR.get(str(value).strip().lower())
            if month_number:
                found[col] = month_number
        if found:
            return row_num, found
    return None, {}


def _year_for_column(col: int, years_by_col: dict[int, int]) -> int:
    candidates = [c for c in years_by_col if c <= col]
    reference_col = max(candidates) if candidates else min(years_by_col)
    return years_by_col[reference_col]


def _read_legend(rows: dict[int, dict[int, str]]) -> dict[str, str]:
    """Best-effort initials -> full name lookup, built from adjacent
    (initials cell, name cell) pairs found anywhere in the sheet. The real
    source file's legend layout is irregular (some entries share a single
    cell), so this intentionally only captures the clean two-cell case
    rather than over-fitting to one file's exact quirks."""
    legend: dict[str, str] = {}
    for cols in rows.values():
        for col, value in cols.items():
            text = str(value).strip()
            if not _INITIALS_RE.match(text):
                continue
            name = str(cols.get(col + 1) or "").strip()
            if name and " " in name:
                legend[text.strip("*").upper()] = name.strip("*").strip()
    return legend
