"""Palette de recherche rapide dédiée à la vue Items (Ctrl+Alt+P)."""
from __future__ import annotations

import unicodedata

from nicegui import ui

from backend.state.store import data_store


_CSS = """
.item-search-dialog { animation: item-search-in 140ms ease-out both; background:var(--bg); color:var(--text);
  border:1px solid var(--border); border-radius:12px; box-shadow:0 18px 50px rgba(31,35,50,.18); }
@keyframes item-search-in { from { opacity:0; transform:translateY(-8px) scale(.98); }
  to { opacity:1; transform:translateY(0) scale(1); } }
.item-search-header { background:var(--bg); border-bottom:1px solid var(--border); }
.item-search-input { color:var(--text); font-size:13px; }
.item-search-input input::placeholder { color:var(--text-dim); }
.item-search-result { transition:background 100ms ease; }
.item-search-result:hover { background:var(--surface); }
.item-search-result.selected { background:var(--surface); }
.item-search-number { color:var(--text-muted); font:11px var(--font-mono); }
.item-search-title { color:var(--text); font-size:13px; font-weight:600; }
.item-search-college { color:var(--text-muted); font-size:11.5px; }
.item-search-hint { color:var(--text-dim); font-size:11px; }
.item-search-kbd { border:1px solid var(--border); border-radius:4px; color:var(--text-muted); font:10.5px var(--font-mono); padding:1px 5px; }
"""


def _fold(value: object) -> str:
    text = str(value or "")
    return "".join(
        char for char in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(char)
    )


def search_items(query: str, courses: list) -> list:
    """Recherche tolérante sur numéro, titre et collèges associés."""
    q = _fold(query).strip()
    if not q:
        return list(courses[:8])

    def score(course) -> tuple[int, str, str]:
        number = _fold(getattr(course, "display_item_number", None) or getattr(course, "item_number", None))
        title = _fold(getattr(course, "title", ""))
        colleges = _fold(" ".join(getattr(course, "college", None) or []))
        if number == q:
            rank = 0
        elif number.startswith(q):
            rank = 1
        elif q in title:
            rank = 2
        elif q in colleges:
            rank = 3
        else:
            return (99, title, number)
        return (rank, title, number)

    return sorted((course for course in courses if score(course)[0] < 99), key=score)[:12]


def open_item_search_palette() -> None:
    """Ouvre la palette Items et navigue directement vers une fiche."""
    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)
    with ui.dialog() as dialog:
        with ui.card().classes(
            "item-search-dialog w-[620px] max-w-[94vw] p-0 overflow-hidden"
        ):
            with ui.element("div").classes("item-search-header flex items-center gap-3 px-4 py-3"):
                ui.icon("search", size="sm").style("color:var(--text-muted)")
                search_input = ui.input(placeholder="Rechercher un item, un titre ou un collège…").props(
                    "autofocus borderless dense"
                ).classes("item-search-input flex-1")
                ui.element("kbd").classes("item-search-kbd").text = "Ctrl+Alt+P"
                ui.button(icon="close", on_click=dialog.close).props("flat round dense color=grey")
            body = ui.column().classes("w-full gap-0").style("max-height:52vh;overflow-y:auto")
            with ui.element("div").classes("px-4 py-2 border-t flex gap-4").style("border-color:var(--border)"):
                ui.label("↑↓ parcourir").classes("item-search-hint")
                ui.label("Entrée ouvrir").classes("item-search-hint")
                ui.label("Échap fermer").classes("item-search-hint")

    state = {"query": "", "selected": 0, "results": []}

    def _open(course) -> None:
        dialog.close()
        ui.navigate.to(f"/cours/{course.id}")

    def _render() -> None:
        body.clear()
        state["results"] = search_items(state["query"], data_store.cours)
        state["selected"] = min(state["selected"], max(0, len(state["results"]) - 1))
        with body:
            if not state["results"]:
                ui.label(f"Aucun item pour « {state['query']} »").classes("px-4 py-8 item-search-hint")
                return
            for index, course in enumerate(state["results"]):
                selected = index == state["selected"]
                row = ui.element("div").classes(
                    "item-search-result w-full px-4 py-3 flex items-center gap-3 cursor-pointer "
                    + (" selected" if selected else "")
                )
                row.on("click", lambda c=course: _open(c))
                with row:
                    ui.label(f"ITEM {course.display_item_number or course.item_number or '—'}").classes("item-search-number w-20 shrink-0")
                    with ui.column().classes("flex-1 gap-0 min-w-0"):
                        ui.label(course.title).classes("item-search-title truncate")
                        colleges = " · ".join(course.college or [])
                        if colleges:
                            ui.label(colleges).classes("item-search-college truncate")

    def _on_change(event) -> None:
        val = getattr(event, "value", None)
        if val is None and hasattr(event, "args"):
            val = event.args
        state["query"] = str(val or "")
        state["selected"] = 0
        _render()

    def _on_key(event) -> None:
        key = getattr(event, "key", "")
        if not key and isinstance(getattr(event, "args", None), dict):
            key = event.args.get("key", "")
        key = getattr(key, "name", key)
        if key in ("ArrowDown", "down"):
            state["selected"] = min(state["selected"] + 1, max(0, len(state["results"]) - 1))
            _render()
        elif key in ("ArrowUp", "up"):
            state["selected"] = max(0, state["selected"] - 1)
            _render()
        elif key in ("Enter", "enter") and state["results"]:
            _open(state["results"][state["selected"]])

    search_input.on("update:model-value", _on_change)
    search_input.on("keydown", _on_key)
    _render()
    dialog.open()
