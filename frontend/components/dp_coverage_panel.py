"""Panneau de couverture des dossiers progressifs par item EDN."""

from __future__ import annotations

from nicegui import ui

from backend.core.qcm.items_mapping import all_items, college_full
from backend.core.reviews import local_store
from backend.state.store import data_store

_CSS = """
.dpc-toolbar { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:10px; }
.dpc-table { border:1px solid var(--border); border-radius:8px; overflow:hidden; min-width:0; flex:0 0 auto; }
.dpc-head { display:grid; grid-template-columns:56px minmax(0,1fr) 64px; align-items:center; gap:10px; padding:6px 12px; font-size:10px;
  text-transform:uppercase; letter-spacing:.04em; color:var(--text-dim); font-weight:600;
  border-bottom:1px solid var(--border); background:var(--bg-alt); }
.dpc-row { display:grid; grid-template-columns:56px minmax(0,1fr) 64px; align-items:center; gap:10px; padding:8px 12px; font-size:12.5px;
  border-bottom:1px solid var(--border); }
.dpc-row:last-child { border-bottom:none; }
.dpc-id { font-family:var(--font-mono); color:var(--text-muted); }
.dpc-main { min-width:0; }
.dpc-title { min-width:0; line-height:1.35; overflow-wrap:anywhere; }
.dpc-college { color:var(--text-muted); font-size:11px; line-height:1.3; margin-top:2px; overflow-wrap:anywhere; }
.dpc-count { min-width:0; text-align:right; font-family:var(--font-mono); font-weight:600; }
.dpc-count.zero { color:var(--danger); }
.dpc-empty { padding:24px 12px; text-align:center; color:var(--text-dim); font-size:12.5px; }
.dpc-summary { font-size:11.5px; color:var(--text-muted); margin-bottom:8px; }
.dpc-scroll { max-height:520px; overflow-y:scroll; overflow-x:hidden; min-width:0; scrollbar-gutter:stable; scrollbar-width:thin; scrollbar-color:var(--border-strong) var(--bg-alt); overscroll-behavior:contain; }
.dpc-scroll::-webkit-scrollbar { width:10px; }
.dpc-scroll::-webkit-scrollbar-track { background:var(--bg-alt); border-left:1px solid var(--border); }
.dpc-scroll::-webkit-scrollbar-thumb { background:var(--border-strong); border:2px solid var(--bg-alt); border-radius:999px; }
.dpc-scroll::-webkit-scrollbar-thumb:hover { background:var(--text-dim); }
@media (max-width:560px) {
  .dpc-head, .dpc-row { grid-template-columns:46px minmax(0,1fr) 52px; gap:8px; padding-left:10px; padding-right:10px; }
}
"""

_SORT_OPTIONS = {
    "item": "Numéro d'item",
    "asc": "Nb DP (croissant)",
    "desc": "Nb DP (décroissant)",
}


def _item_number(value: object) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _coverage_rows(courses, counts: dict[str, int]) -> list[dict]:
    """Agrège le référentiel EDN et les rattachements réels des cours.

    Le référentiel associe un item à son collège principal. Les cours Synapse
    peuvent en ajouter plusieurs ; chacun reste visible dans le filtre du
    collège concerné, sans dupliquer l'item dans la liste.
    """
    by_item: dict[int, dict] = {}
    for entry in all_items():
        item = _item_number(entry.get("item"))
        if item is None:
            continue
        primary_college = college_full(entry.get("college", ""))
        by_item[item] = {
            "item": item,
            "title": str(entry.get("title", "") or ""),
            "colleges": {primary_college} if primary_college else set(),
        }

    for course in courses or []:
        item = _item_number(getattr(course, "item_number", ""))
        if item is None:
            continue
        row = by_item.setdefault(item, {
            "item": item,
            "title": str(getattr(course, "title", "") or ""),
            "colleges": set(),
        })
        if not row["title"]:
            row["title"] = str(getattr(course, "title", "") or "")
        row["colleges"].update(
            str(college).strip() for college in (getattr(course, "college", None) or [])
            if str(college).strip()
        )

    return [
        {**row, "count": counts.get(str(item), 0)}
        for item, row in by_item.items()
    ]


def render(container: ui.element) -> None:
    with container:
        ui.add_head_html(f"<style>{_CSS}</style>", shared=True)
        ui.label("COUVERTURE DP PAR ITEM").classes("se-label")

        all_rows = _coverage_rows(getattr(data_store, "cours", []) or [], {})
        colleges = sorted({college for row in all_rows for college in row["colleges"]})
        state = {"college": "Tous", "only_missing": False, "sort": "item"}

        toolbar = ui.element("div").classes("dpc-toolbar")
        summary = ui.label().classes("dpc-summary")
        table = ui.column().classes("w-full gap-0 dpc-scroll")

        def _rows() -> list[dict]:
            rows = _coverage_rows(
                getattr(data_store, "cours", []) or [],
                local_store.get_dp_count_by_item(),
            )
            if state["college"] != "Tous":
                rows = [row for row in rows if state["college"] in row["colleges"]]
            if state["only_missing"]:
                rows = [row for row in rows if row["count"] == 0]
            if state["sort"] == "asc":
                rows.sort(key=lambda row: (row["count"], row["item"]))
            elif state["sort"] == "desc":
                rows.sort(key=lambda row: (-row["count"], row["item"]))
            else:
                rows.sort(key=lambda row: row["item"])
            return rows

        def _redraw() -> None:
            rows = _rows()
            zero = sum(row["count"] == 0 for row in rows)
            summary.set_text(f"{len(rows)} item(s) affiché(s) · {zero} sans aucun DP")
            table.clear()
            with table:
                with ui.element("div").classes("dpc-table"):
                    with ui.element("div").classes("dpc-head"):
                        ui.label("ITEM").classes("dpc-id")
                        ui.label("TITRE").classes("dpc-title")
                        ui.label("NB DP").classes("dpc-count")
                    if not rows:
                        ui.label("Aucun item pour ce filtrage.").classes("dpc-empty")
                    for row in rows:
                        with ui.element("div").classes("dpc-row"):
                            ui.label(str(row["item"])).classes("dpc-id")
                            with ui.column().classes("dpc-main gap-0"):
                                ui.label(row["title"]).classes("dpc-title")
                                if state["college"] == "Tous" and row["colleges"]:
                                    ui.label(" · ".join(sorted(row["colleges"]))).classes("dpc-college")
                            ui.label(str(row["count"])).classes(
                                "dpc-count zero" if row["count"] == 0 else "dpc-count"
                            )

        def _on_college(value: str) -> None:
            state["college"] = value or "Tous"
            _redraw()

        def _on_sort(value: str) -> None:
            state["sort"] = next((key for key, label in _SORT_OPTIONS.items() if label == value), "item")
            _redraw()

        def _on_toggle(value: bool) -> None:
            state["only_missing"] = bool(value)
            _redraw()

        with toolbar:
            ui.select(
                ["Tous", *colleges], value="Tous", label="Collège",
                on_change=lambda event: _on_college(event.value),
            ).props("outlined dense options-dense").classes("w-64")
            ui.select(
                list(_SORT_OPTIONS.values()), value=_SORT_OPTIONS["item"], label="Trier par",
                on_change=lambda event: _on_sort(event.value),
            ).props("outlined dense options-dense").classes("w-52")
            ui.checkbox("Seulement sans DP", value=False, on_change=lambda event: _on_toggle(event.value))

        _redraw()
