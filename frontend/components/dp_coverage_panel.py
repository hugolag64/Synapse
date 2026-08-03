"""Panneau « Couverture DP par item » pour Paramètres — combien de Dossiers
Progressifs couvrent chaque item du référentiel EDN, pour repérer ceux à
créer manuellement (ChatGPT/Gemini) plutôt qu'à l'aveugle. Volontairement en
dehors de la vue Items (tunnelisée sur un autre usage) — vue d'ensemble
séparée, avec collège/tri/filtre dédiés.

Kept out of settings_cockpit.py to keep that file to layout/wiring only
(même convention que uness_diagnostic_panel.py)."""

from __future__ import annotations

from nicegui import ui

from backend.core.qcm.items_mapping import all_items, college_full
from backend.core.reviews import local_store

_CSS = """
.dpc-toolbar { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:10px; }
.dpc-table { border:1px solid var(--border); border-radius:8px; overflow:hidden; }
.dpc-head { display:flex; align-items:center; gap:10px; padding:6px 12px; font-size:10px;
  text-transform:uppercase; letter-spacing:.04em; color:var(--text-dim); font-weight:600;
  border-bottom:1px solid var(--border); background:var(--bg-alt); }
.dpc-row { display:flex; align-items:center; gap:10px; padding:6px 12px; font-size:12.5px;
  border-bottom:1px solid var(--border); }
.dpc-row:last-child { border-bottom:none; }
.dpc-id { flex:0 0 46px; font-family:var(--font-mono); color:var(--text-muted); }
.dpc-title { flex:1 1 auto; min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.dpc-college { flex:0 0 190px; color:var(--text-muted); font-size:11.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.dpc-count { flex:0 0 70px; text-align:right; font-family:var(--font-mono); font-weight:600; }
.dpc-count.zero { color:var(--danger); }
.dpc-empty { padding:24px 12px; text-align:center; color:var(--text-dim); font-size:12.5px; }
.dpc-summary { font-size:11.5px; color:var(--text-muted); margin-bottom:8px; }
.dpc-scroll { max-height:440px; overflow-y:auto; }
"""

_SORT_OPTIONS = {
    "item": "Numéro d'item",
    "asc": "Nb DP (croissant)",
    "desc": "Nb DP (décroissant)",
}


def render(container: ui.element) -> None:
    with container:
        ui.add_head_html(f"<style>{_CSS}</style>", shared=True)
        ui.label("COUVERTURE DP PAR ITEM").classes("se-label")

        colleges = sorted({college_full(e.get("college", "")) for e in all_items() if college_full(e.get("college", ""))})
        state = {"college": "Tous", "only_missing": False, "sort": "item"}

        toolbar = ui.element("div").classes("dpc-toolbar")
        summary = ui.label().classes("dpc-summary")
        table = ui.column().classes("w-full gap-0 dpc-scroll")

        def _rows() -> list[dict]:
            counts = local_store.get_dp_count_by_item()
            items = all_items()
            if state["college"] != "Tous":
                items = [e for e in items if college_full(e.get("college", "")) == state["college"]]
            rows = [
                {
                    "item": e["item"],
                    "title": e.get("title", ""),
                    "college": college_full(e.get("college", "")) or "—",
                    "count": counts.get(str(e["item"]), 0),
                }
                for e in items
            ]
            if state["only_missing"]:
                rows = [r for r in rows if r["count"] == 0]
            if state["sort"] == "asc":
                rows.sort(key=lambda r: r["count"])
            elif state["sort"] == "desc":
                rows.sort(key=lambda r: -r["count"])
            else:
                rows.sort(key=lambda r: r["item"])
            return rows

        def _redraw() -> None:
            rows = _rows()
            total = len(rows)
            zero = sum(1 for r in rows if r["count"] == 0)
            summary.set_text(f"{total} item(s) affiché(s) · {zero} sans aucun DP")
            table.clear()
            show_college = state["college"] == "Tous"
            with table:
                with ui.element("div").classes("dpc-table"):
                    with ui.element("div").classes("dpc-head"):
                        ui.label("ITEM").classes("dpc-id")
                        ui.label("TITRE").classes("dpc-title")
                        if show_college:
                            ui.label("COLLÈGE").classes("dpc-college")
                        ui.label("NB DP").classes("dpc-count")
                    if not rows:
                        ui.label("Aucun item pour ce filtrage.").classes("dpc-empty")
                    else:
                        for r in rows:
                            with ui.element("div").classes("dpc-row"):
                                ui.label(str(r["item"])).classes("dpc-id")
                                ui.label(r["title"]).classes("dpc-title")
                                if show_college:
                                    ui.label(r["college"]).classes("dpc-college")
                                ui.label(str(r["count"])).classes(
                                    "dpc-count zero" if r["count"] == 0 else "dpc-count"
                                )

        def _on_college(value: str) -> None:
            state["college"] = value or "Tous"
            _redraw()

        def _on_sort(value: str) -> None:
            state["sort"] = next((k for k, v in _SORT_OPTIONS.items() if v == value), "item")
            _redraw()

        def _on_toggle(value: bool) -> None:
            state["only_missing"] = bool(value)
            _redraw()

        with toolbar:
            ui.select(
                ["Tous", *colleges], value="Tous", label="Collège",
                on_change=lambda e: _on_college(e.value),
            ).props("outlined dense options-dense").classes("w-64")
            ui.select(
                list(_SORT_OPTIONS.values()), value=_SORT_OPTIONS["item"], label="Trier par",
                on_change=lambda e: _on_sort(e.value),
            ).props("outlined dense options-dense").classes("w-52")
            ui.checkbox("Seulement sans DP", value=False, on_change=lambda e: _on_toggle(e.value))

        _redraw()
