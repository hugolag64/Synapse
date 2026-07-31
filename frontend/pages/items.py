"""items.py — Vue « Items » (refonte, session 9, écran nouveau).

Liste transverse filtrable de tous les items médicaux.

Point d'entrée attendu par la « retard » cliquable de Collèges (session 7,
`?college=`) : filtre initial sur ce collège, colonne Collège masquée au
profit de « Dernière révision » (README §7).

Écarts assumés (voir Journal du CLAUDE.md de la refonte) :
  • chips = sélection unique (Tous / <collège navigué> / Fragile-critique /
    En retard), pas des filtres indépendants cumulables — cohérent avec la
    capture (un seul chip actif à la fois) ;
  • « type » dérivé simplement (LACUNE si lacune active, sinon PDF si
    ressource liée, sinon NOTE) — pas de distinction QCM/RAPPEL faute de
    signal fiable par cours (contrairement aux ReviewTask de Révisions) ;
  • « dernière révision » = date de la session la plus récente
    (`study_sessions`), aucune session → « — » ; couleur = fraîcheur
    (≤7 j vert, ≤30 j ambre, plus ancien ou jamais = gris), pas de grille
    officielle donnée par le README pour ce point.
"""
from __future__ import annotations

import datetime

from nicegui import ui
from starlette.requests import Request

from frontend.theme import frame
from backend.state.store import data_store
from backend.core.reviews.local_store import (
    get_all_history, get_sessions_by_course, get_postpone_counts,
    get_qcm_done_course_ids, get_active_lacunes_count_by_course,
)
from backend.core.reviews.service import review_service
from backend.core.reviews.mastery import get_course_mastery
from frontend.components.study_task_row import _ring_glyph, due_info
from frontend.components.mastery_indicator import mastery_indicator, ensure_styles as _mastery_styles
from frontend.components.item_search_palette import open_item_search_palette

_CSS = """
.it-wrap { max-width:1200px; width:100%; min-width:0; overflow:hidden; }
.it-topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; padding:4px 0 14px; flex-wrap:wrap; }
.it-title { font-size:20px; font-weight:600; color:var(--text); letter-spacing:-0.01em; }
.it-subtitle { font-size:12.5px; color:var(--text-muted); margin-top:4px; }
.it-search { display:flex; align-items:center; gap:8px; height:32px; padding:0 10px; border:1px solid var(--border);
  border-radius:6px; color:var(--text-dim); font-size:12px; cursor:pointer; background:var(--bg); flex:0 0 auto; }
.it-search:hover { border-color:var(--border-strong); }
.it-search kbd { font-family:var(--font-mono); font-size:10.5px; border:1px solid var(--border); border-radius:4px; padding:0 4px; }
.it-chips-row { display:flex; align-items:center; gap:10px; margin-bottom:14px; flex-wrap:wrap; }
.it-chips { display:flex; gap:6px; flex-wrap:wrap; }
.it-chip { font-size:12px; font-weight:500; padding:5px 12px; border-radius:6px; cursor:pointer;
  color:var(--text-muted); border:1px solid var(--border); background:var(--bg);
  transition: background var(--duration-fast) var(--ease-standard),
              color var(--duration-fast) var(--ease-standard),
              border-color var(--duration-fast) var(--ease-standard); }
.it-chip:hover { background:var(--surface); }
.it-chip.active { background:var(--accent); border-color:var(--accent); color:var(--accent-text); }
.it-filter-hint { font-size:11.5px; color:var(--text-dim); font-style:italic; }
.it-head { display:flex; align-items:center; gap:12px; padding:0 10px 8px; font-size:10px;
  text-transform:uppercase; letter-spacing:.04em; color:var(--text-dim); font-weight:600;
  border-bottom:1px solid var(--border); }
.it-h-ring { flex:0 0 16px; }
.it-h-id { flex:0 0 46px; }
.it-h-title { flex:1 1 auto; }
.it-h-college { flex:0 0 160px; }
.it-h-type { flex:0 0 70px; }
.it-h-mastery { flex:0 0 140px; }
.it-h-next { flex:0 0 84px; }
.it-row { display:flex; align-items:center; gap:12px; height:44px; width:100%; min-width:0; padding:0 10px; border-bottom:1px solid var(--border);
  cursor:pointer; color:var(--text); text-decoration:none; transition: background var(--duration-fast) var(--ease-standard); }
.it-row:hover { background:var(--surface); }
.it-row:last-child { border-bottom:none; }
.it-ring { font-size:14px; color:var(--text-muted); flex:0 0 16px; text-align:center; }
.it-id { font-family:var(--font-mono); font-size:11.5px; color:var(--text-muted); flex:0 0 46px; }
.it-title-cell { flex:1 1 auto; min-width:0; font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.it-college { flex:0 0 160px; font-size:12px; color:var(--text-muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.it-last { flex:0 0 160px; display:flex; align-items:center; gap:6px; font-size:12px; color:var(--text-muted); }
.it-last-dot { width:6px; height:6px; border-radius:50%; flex:0 0 6px; }
.it-type { font-family:var(--font-mono); font-size:10px; letter-spacing:.03em; color:var(--text-muted);
  border:1px solid var(--border); border-radius:4px; padding:1px 5px; flex:0 0 70px; text-align:center; }
.it-mastery { flex:0 0 140px; }
.it-next { display:flex; align-items:center; gap:5px; flex:0 0 84px; font-size:11.5px; color:var(--text-muted); }
.it-next-dot { width:6px; height:6px; border-radius:50%; flex:0 0 6px; }
.it-empty { padding:32px 10px; text-align:center; color:var(--text-dim); font-size:13px; }
@media (max-width: 900px) {
  .it-college, .it-h-college { flex-basis:120px; }
  .it-mastery, .it-h-mastery { flex-basis:110px; }
  .it-next, .it-h-next { flex-basis:70px; }
}
"""


def _safe_item_number(n: str | None) -> float:
    if not n:
        return 999999.0
    try:
        return float(n.replace(",", "."))
    except ValueError:
        return 999999.0


def _sort_item_rows(rows: list[dict], mode: str = "item") -> list[dict]:
    """Trie sans dupliquer les items multi-collèges."""
    if mode == "college":
        return sorted(
            rows,
            key=lambda r: (
                (r["course"].college or [""])[0].casefold(),
                _safe_item_number(r["course"].item_number),
                r["course"].title.casefold(),
            ),
        )
    return sorted(
        rows,
        key=lambda r: (_safe_item_number(r["course"].item_number), r["course"].title.casefold()),
    )
def _last_review_info(sessions: list) -> tuple[str, str]:
    """(couleur token, libellé relatif) à partir des study_sessions d'un cours."""
    if not sessions:
        return "var(--text-dim)", "—"
    dates = [s["session_date"] for s in sessions if s["session_date"]]
    if not dates:
        return "var(--text-dim)", "—"
    last = max(datetime.date.fromisoformat(d[:10]) for d in dates)
    delta = (datetime.date.today() - last).days
    if delta <= 0:
        label = "auj."
    elif delta == 1:
        label = "hier"
    else:
        label = f"il y a {delta}j"
    if delta <= 7:
        color = "var(--success)"
    elif delta <= 30:
        color = "var(--warning)"
    else:
        color = "var(--text-dim)"
    return color, label


def _type_tag(course, lacune_ids: set[str]) -> str:
    if course.id in lacune_ids:
        return "LACUNE"
    if course.url_pdf:
        return "PDF"
    return "NOTE"


@ui.page('/items')
@frame('Items')
def items_page(request: Request) -> None:
    if not data_store.is_loaded:
        ui.label("Chargement des données…").classes("text-slate-500")
        return

    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)
    _mastery_styles()

    college_param = request.query_params.get("college") or None
    filt = {"mode": "college" if college_param else "all", "sort": "item",
            "college": college_param or "Tous"}

    with ui.column().classes("it-wrap gap-0"):
        topbar = ui.element("div").classes("it-topbar")
        chips_row = ui.element("div").classes("it-chips-row")
        head = ui.element("div").classes("it-head")
        list_col = ui.column().classes("w-full gap-0")

    def _compute() -> list[dict]:
        courses = [c for c in data_store.cours if c.college]

        history = get_all_history()
        sessions_map = get_sessions_by_course()
        postpone_map = get_postpone_counts()
        qcm_done_set = get_qcm_done_course_ids()
        lacune_counts = get_active_lacunes_count_by_course()
        lacune_ids = {cid for cid, n in lacune_counts.items() if n > 0}

        all_tasks = review_service.generate_reviews(
            context="college", history=history,
            sessions_map=sessions_map, postpone_map=postpone_map,
        )
        urgent_ids = {t.course_id for t in review_service.get_urgent_tasks(all_tasks)}
        next_by_course: dict[str, object] = {}
        for t in all_tasks:
            cur = next_by_course.get(t.course_id)
            if cur is None or t.due_date < cur.due_date:
                next_by_course[t.course_id] = t

        qcm_trends = local_store.get_qcm_latest_by_course()
        rows = []
        for c in courses:
            sessions = sessions_map.get(c.id, [])
            mastery = get_course_mastery(
                c, context="college", sessions=sessions,
                total_postpone=postpone_map.get(c.id, 0),
                qcm_done_local=(c.id in qcm_done_set),
            )
            qcm_info = qcm_trends.get(c.id, {})
            rows.append({
                "course": c,
                "mastery_score": mastery.score,
                "mastery_level": mastery.level,
                "qcm_score": qcm_info.get("last_score"),
                "qcm_trend": qcm_info.get("trend"),
                "type_tag": _type_tag(c, lacune_ids),
                "next_task": next_by_course.get(c.id),
                "sessions": sessions,
                "overdue": c.id in urgent_ids,
            })
        return _sort_item_rows(rows, filt["sort"])

    def _visible(rows: list[dict]) -> list[dict]:
        mode = filt["mode"]
        if filt["college"] != "Tous":
            return [r for r in rows if filt["college"] in (r["course"].college or [])]
        if mode == "fragile":
            return [r for r in rows if r["mastery_level"] in ("fragile", "critique")]
        if mode == "overdue":
            return [r for r in rows if r["overdue"]]
        return rows

    def _draw_topbar() -> None:
        topbar.clear()
        with topbar:
            with ui.column().classes("gap-0"):
                ui.label("Items").classes("it-title")
                ui.label("Tous les items médicaux · cliquez pour ouvrir le détail").classes("it-subtitle")
            search = ui.element("div").classes("it-search")
            with search:
                ui.label("⌕")
                ui.label("Filtrer")
                ui.html("<kbd>Ctrl+Alt+P</kbd>")
            search.on("click", open_item_search_palette)

    def _select(mode: str) -> None:
        filt["mode"] = mode
        _draw_chips()
        _draw_head()
        _draw_list(_all_rows["value"])

    def _draw_chips() -> None:
        chips_row.clear()
        with chips_row:
            with ui.element("div").classes("it-chips"):
                def _chip(label: str, mode: str) -> None:
                    el = ui.element("div").classes(
                        "it-chip active" if filt["mode"] == mode else "it-chip")
                    with el:
                        ui.label(label)
                    el.on("click", lambda m=mode: _select(m))

                _chip("Tous", "all")
                if college_param:
                    _chip(college_param, "college")
                _chip("Fragile / critique", "fragile")
                _chip("En retard", "overdue")

            if filt["mode"] == "college" and college_param:
                ui.label(f"Filtré sur {college_param}").classes("it-filter-hint")

            ui.label("Trier par").classes("it-filter-hint")
            for label, mode in (("Item", "item"), ("Collège", "college")):
                el = ui.element("div").classes(
                    "it-chip active" if filt["sort"] == mode else "it-chip"
                )
                with el:
                    ui.label(label)
                el.on("click", lambda m=mode: _select_sort(m))

            colleges = sorted({name for c in data_store.cours for name in (c.college or [])})
            ui.select(
                ["Tous", *colleges], value=filt["college"], label="Collège",
                on_change=lambda e: _select_college(e.value),
            ).props("outlined dense options-dense").classes("w-52")

    def _select_sort(mode: str) -> None:
        filt["sort"] = mode
        _draw_chips()
        _draw_list(_all_rows["value"])

    def _select_college(name: str) -> None:
        filt["college"] = name or "Tous"
        filt["mode"] = "college" if name and name != "Tous" else "all"
        _draw_chips()
        _draw_head()
        _draw_list(_all_rows["value"])

    def _draw_head() -> None:
        head.clear()
        show_college = filt["college"] == "Tous"
        with head:
            ui.label("").classes("it-h-ring")
            ui.label("ITEM").classes("it-h-id")
            ui.label("TITRE").classes("it-h-title")
            ui.label("COLLÈGE" if show_college else "DERNIÈRE RÉVISION").classes("it-h-college")
            ui.label("TYPE").classes("it-h-type")
            ui.label("MAÎTRISE").classes("it-h-mastery")
            ui.label("PROCHAINE").classes("it-h-next")

    def _draw_row(r: dict) -> None:
        c = r["course"]
        show_college = filt["college"] == "Tous"
        row = ui.element("div").classes("it-row")
        row.on("click", lambda cid=c.id: ui.navigate.to(f"/cours/{cid}"))
        with row:
            ui.label(_ring_glyph(r["mastery_score"])).classes("it-ring")
            ui.label(c.item_number or "—").classes("it-id")
            ui.label(c.title).classes("it-title-cell")
            if show_college:
                college = " · ".join(c.college or [""])
                ui.label(college).classes("it-college")
            else:
                color, label = _last_review_info(r["sessions"])
                with ui.element("div").classes("it-last"):
                    ui.element("span").classes("it-last-dot").style(f"background:{color}")
                    ui.label(label)
            ui.label(r["type_tag"]).classes("it-type")
            with ui.element("div").classes("it-mastery flex items-center gap-2"):
                mastery_indicator(r["mastery_score"], r["mastery_level"])
                q_score = r.get("qcm_score")
                if q_score is not None:
                    trend = r.get("qcm_trend") or ""
                    ui.label(f"{int(q_score)}% {trend}").classes("text-[11px] font-mono text-slate-500 font-semibold bg-slate-100 px-1.5 py-0.5 rounded")
            with ui.element("div").classes("it-next"):
                nt = r["next_task"]
                if nt is None:
                    ui.label("—")
                else:
                    color, label = due_info(nt)
                    ui.element("span").classes("it-next-dot").style(f"background:{color}")
                    ui.label(label)

    def _draw_list(rows: list[dict]) -> None:
        list_col.clear()
        visible = _visible(rows)
        with list_col:
            if not visible:
                with ui.element("div").classes("it-empty"):
                    ui.label("Aucun item pour ce filtrage.")
                return
            for r in visible:
                _draw_row(r)

    _all_rows = {"value": []}

    def _render() -> None:
        _all_rows["value"] = _compute()
        _draw_topbar()
        _draw_chips()
        _draw_head()
        _draw_list(_all_rows["value"])

    _render()

    from frontend.keybindings import register_item_search_keybinding
    register_item_search_keybinding(open_item_search_palette)
