"""Builds a minimal .xlsx (inline strings, no sharedStrings.xml) for parser tests."""
from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


def _col_letter(idx: int) -> str:
    letters = ""
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _cell_xml(ref: str, text: str) -> str:
    return f'<c r="{ref}" t="inlineStr"><is><t>{escape(text)}</t></is></c>'


def _row_xml(row_num: int, cells: dict[int, str]) -> str:
    cell_xml = "".join(
        _cell_xml(f"{_col_letter(col)}{row_num}", text)
        for col, text in sorted(cells.items())
        if text is not None
    )
    return f'<row r="{row_num}">{cell_xml}</row>'


def write_minimal_xlsx(path: Path, rows: dict[int, dict[int, str]]) -> None:
    rows_xml = "".join(_row_xml(r, cells) for r, cells in sorted(rows.items()))
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{rows_xml}</sheetData></worksheet>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
