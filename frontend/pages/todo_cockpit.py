"""todo_cockpit.py — Vue « Révisions » cockpit (refonte, session 5).

Rendu quand preferences['ui_mode'] == 'cockpit' (early-return depuis todo.py).
File des tâches de répétition espacée (J3/J7/J14/J30) — chips de filtre par
cycle, ligne dense par tâche, bouton Réviser → Mode Focus existant (aucun
dialog de validation réimplémenté). Le chemin classic (routine/ajouté/note)
reste strictement inchangé.

Écarts assumés (Journal du CLAUDE.md de la refonte) :
  • callbacks _on_done/_on_postpone/_on_ignore copiés depuis _cockpit_today.py
    (même limitation déjà actée : à dédupliquer quand classic sera retiré) ;
  • fenêtre affichée = en retard + aujourd'hui + 7 j à venir (le mockup ne
    donne pas de borne explicite ; generate_reviews irait jusqu'à 30 j, ce qui
    noierait la file) ;
  • étiquette « type » dérivée de la présence d'un PDF réel (url_pdf/url_pdf_ue)
    plutôt que réutiliser telle quelle study_task_row.type_tag — cette file ne
    contient que des cycles J3–J30 (jamais qcm_error/consolidation/lacune), la
    fonction partagée retomberait donc systématiquement sur « NOTE ».
"""
from __future__ import annotations

import datetime

from nicegui import ui

from backend.core.reviews import local_store
from backend.core.reviews.validation import complete_review
from backend.core.reviews.service import review_service
from backend.core.notion.service import notion_service
from backend.state.store import data_store

from frontend.pages.dashboard._state import DashboardState
from frontend.pages.dashboard._reviews import open_focus_mode
from frontend.components.study_task_row import due_info, ensure_styles as _row_styles
from frontend.components.mastery_indicator import mastery_indicator, ensure_styles as _mastery_styles

_CYCLES = ["J3", "J7", "J14", "J30"]

_CSS = """
.rv-wrap { max-width:1200px; width:100%; }
.rv-topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; padding:4px 0 18px; }
.rv-title { font-size:20px; font-weight:600; color:var(--text); letter-spacing:-0.01em; }
.rv-subtitle { display:flex; align-items:center; gap:4px; flex-wrap:wrap; font-size:12.5px;
  color:var(--text-muted); margin-top:4px; }
.rv-chips { display:flex; gap:6px; margin-bottom:16px; }
.rv-chip { font-size:12px; font-weight:500; padding:5px 12px; border-radius:6px; cursor:pointer;
  color:var(--text-muted); border:1px solid var(--border); background:var(--bg);
  transition: background var(--duration-fast) var(--ease-standard),
              color var(--duration-fast) var(--ease-standard),
              border-color var(--duration-fast) var(--ease-standard); }
.rv-chip:hover { background:var(--surface); }
.rv-chip.active { background:var(--accent); border-color:var(--accent); color:var(--accent-text); }
.rv-head { display:flex; align-items:center; gap:12px; padding:0 10px 8px; font-size:10px;
  text-transform:uppercase; letter-spacing:.04em; color:var(--text-dim); font-weight:600;
  border-bottom:1px solid var(--border); }
.rv-h-cycle { flex:0 0 40px; }
.rv-h-id { flex:0 0 46px; }
.rv-h-main { flex:1 1 auto; }
.rv-h-mastery { flex:0 0 140px; }
.rv-h-due { flex:0 0 84px; }
.rv-h-action { flex:0 0 84px; }
.rv-row { display:flex; align-items:center; gap:12px; min-height:44px; padding:8px 10px;
  border-bottom:1px solid var(--border); }
.rv-row:last-child { border-bottom:none; }
.rv-cycle { font-family:var(--font-mono); font-size:11px; color:var(--text-muted); flex:0 0 40px; }
.rv-id { font-family:var(--font-mono); font-size:11.5px; color:var(--text-muted); flex:0 0 46px; }
.rv-main { flex:1 1 auto; min-width:0; }
.rv-course-title { font-size:13.5px; color:var(--text); line-height:1.3; }
.rv-course-sub { font-size:11.5px; color:var(--text-dim); margin-top:2px;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.rv-mastery { flex:0 0 140px; }
.rv-due { display:flex; align-items:center; gap:5px; flex:0 0 84px; font-size:11.5px; color:var(--text-muted); }
.rv-due-dot { width:6px; height:6px; border-radius:50%; flex:0 0 6px; }
.rv-action { flex:0 0 84px; display:flex; justify-content:flex-end; }
.rv-btn-primary { background:var(--accent); color:var(--accent-text); border-radius:6px; padding:9px 16px;
  font-size:13px; font-weight:500; cursor:pointer; white-space:nowrap; }
.rv-btn-primary:hover { background:var(--accent-hover); }
.rv-btn-sm { background:var(--accent); color:var(--accent-text); border-radius:6px; padding:6px 12px;
  font-size:12px; font-weight:500; cursor:pointer; white-space:nowrap; }
.rv-btn-sm:hover { background:var(--accent-hover); }
.rv-empty { padding:32px 10px; text-align:center; color:var(--text-dim); font-size:13px; }
"""


def _type_tag(t) -> str:
    return "PDF" if (t.url_pdf or t.url_pdf_ue) else "NOTE"


async def render_revisions_cockpit() -> None:
    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)
    _row_styles()
    _mastery_styles()

    state = DashboardState()
    data: dict = {"tasks": [], "overdue": 0}
    filt: dict = {"cycle": None}  # None = Toutes

    # ── Callbacks Mode Focus (copiés depuis _cockpit_today.py — voir Journal) ──
    async def _on_done(task, card=None, activity_types=None, duration_minutes=None,
                        confidence=None, difficulty=None, qcm_result=None,
                        weak_category=None, weak_detail=None) -> None:
        complete_review(
            task,
            activity_types=activity_types,
            duration_minutes=duration_minutes,
            confidence=confidence,
            difficulty=difficulty,
            qcm_result=qcm_result,
            weak_category=weak_category,
            weak_detail=weak_detail,
        )
        ui.notify(f"✓ Révisé : {task.course_title}", type="positive")
        _load_and_render()

        async def _sync():
            c = next((x for x in data_store.cours if x.id == task.course_id), None)
            if not c:
                return
            ok = await notion_service.increment_lecture_college(c.id, c.nb_lectures)
            if ok:
                c.nb_lectures += 1
                data_store.save_to_disk()

        import asyncio
        asyncio.create_task(_sync())

    async def _on_postpone(task, card=None, days: int = 1) -> None:
        new_date = task.due_date + datetime.timedelta(days=days)
        local_store.postpone(
            task_id=task.id, course_id=task.course_id, context=task.context,
            review_type=task.review_type, theoretical_due_date=task.theoretical_due_date,
            postponed_to=new_date, course_title=task.course_title,
            item_number=task.item_number or "",
        )
        ui.notify(f"Reporté au {new_date.strftime('%d/%m')} : {task.course_title}", type="info")
        _load_and_render()

    async def _on_ignore(task, card=None) -> None:
        local_store.ignore(
            task_id=task.id, course_id=task.course_id, context=task.context,
            review_type=task.review_type, theoretical_due_date=task.theoretical_due_date,
            course_title=task.course_title, item_number=task.item_number or "",
        )
        ui.notify(f"Ignoré : {task.course_title}", type="warning")
        _load_and_render()

    state._on_done = _on_done
    state._on_postpone = _on_postpone
    state._on_ignore = _on_ignore

    # ── Layout ──────────────────────────────────────────────────────────────
    with ui.column().classes("rv-wrap gap-0"):
        topbar = ui.element("div").classes("rv-topbar")
        chips_row = ui.element("div").classes("rv-chips")
        list_col = ui.column().classes("w-full gap-0")

    def _visible_tasks() -> list:
        if filt["cycle"] is None:
            return data["tasks"]
        return [t for t in data["tasks"] if t.review_type == filt["cycle"]]

    def _start_queue() -> None:
        tasks = _visible_tasks()
        if not tasks:
            ui.notify("Aucune révision dans cette file.", type="info")
            return
        state.focus_tasks = list(tasks)
        open_focus_mode(state)

    def _review_one(t) -> None:
        state.focus_tasks = [t]
        open_focus_mode(state)

    def _draw_topbar() -> None:
        topbar.clear()
        with topbar:
            with ui.column().classes("gap-0"):
                ui.label("Révisions").classes("rv-title")
                with ui.element("div").classes("rv-subtitle"):
                    ui.label(f"{len(data['tasks'])} dues ·")
                    ui.label(f"{data['overdue']} en retard").style(
                        "color:var(--danger); font-weight:500;")
                    ui.label("· répétition espacée J3/J7/J14/J30")
            btn = ui.element("div").classes("rv-btn-primary")
            with btn:
                ui.label("Démarrer la file")
            btn.on("click", _start_queue)

    def _select_cycle(value) -> None:
        filt["cycle"] = value
        _draw_chips()
        _draw_list()

    def _draw_chips() -> None:
        chips_row.clear()
        with chips_row:
            def _chip(label: str, value) -> None:
                el = ui.element("div").classes(
                    "rv-chip active" if filt["cycle"] == value else "rv-chip")
                with el:
                    ui.label(label)
                el.on("click", lambda v=value: _select_cycle(v))

            _chip("Toutes", None)
            for c in _CYCLES:
                _chip(c, c)

    def _draw_list() -> None:
        list_col.clear()
        tasks = _visible_tasks()
        with list_col:
            if not tasks:
                with ui.element("div").classes("rv-empty"):
                    ui.label("Aucune révision dans cette file.")
                return
            with ui.element("div").classes("rv-head"):
                ui.label("CYCLE").classes("rv-h-cycle")
                ui.label("ITEM").classes("rv-h-id")
                ui.label("COURS").classes("rv-h-main")
                ui.label("MAÎTRISE").classes("rv-h-mastery")
                ui.label("ÉCHÉANCE").classes("rv-h-due")
                ui.element("div").classes("rv-h-action")
            for t in tasks:
                _draw_row(t)

    def _draw_row(t) -> None:
        college = (t.college or [""])[0] if t.college else ""
        due_color, due_label = due_info(t)
        sub = " · ".join(x for x in [college, _type_tag(t)] if x)
        with ui.element("div").classes("rv-row"):
            ui.label(t.review_type).classes("rv-cycle")
            ui.label(t.item_number or "—").classes("rv-id")
            with ui.element("div").classes("rv-main"):
                ui.label(t.course_title).classes("rv-course-title")
                if sub:
                    ui.label(sub).classes("rv-course-sub")
            with ui.element("div").classes("rv-mastery"):
                mastery_indicator(t.mastery_score, t.mastery_level)
            with ui.element("div").classes("rv-due"):
                ui.element("span").classes("rv-due-dot").style(f"background:{due_color}")
                ui.label(due_label)
            with ui.element("div").classes("rv-action"):
                rbtn = ui.element("div").classes("rv-btn-sm")
                with rbtn:
                    ui.label("Réviser")
                rbtn.on("click", lambda t=t: _review_one(t))

    def _load_and_render() -> None:
        history = local_store.get_all_history()
        base = review_service.generate_reviews(context="college", history=history)
        urgent = review_service.get_urgent_tasks(base)
        today_tasks = review_service.get_today_tasks(base)
        upcoming = review_service.get_upcoming_tasks(base, days=7)
        data["tasks"] = urgent + today_tasks + upcoming
        data["overdue"] = len(urgent)
        _draw_topbar()
        _draw_chips()
        _draw_list()

    _load_and_render()
