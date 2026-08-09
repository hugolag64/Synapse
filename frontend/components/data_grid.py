"""Small shared contract for aligned headers and data rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class GridColumn:
    key: str
    label: str
    width: str


@dataclass(frozen=True)
class DataGrid:
    columns: tuple[GridColumn, ...]

    def __init__(self, columns: Iterable[GridColumn]):
        object.__setattr__(self, "columns", tuple(columns))

    @property
    def column_template(self) -> str:
        return " ".join(column.width for column in self.columns)

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(column.label for column in self.columns)


def grid_style(grid: DataGrid) -> str:
    return f"grid-template-columns:{grid.column_template};"
