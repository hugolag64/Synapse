"""study_task_row — ligne dense de la file de travail (refonte cockpit).

Six dimensions de statut, une seule par la couleur :
  • Progression (workflow) → forme d'anneau (○◔◑◕◉●), couleur neutre.
  • Urgence / retard       → couleur (rouge retard · ambre auj. · vert à jour · gris non planifié).
  • Type d'activité        → étiquette mono (PDF/NOTE/QCM/CONSO/LACUNE).
  • Charge / temps         → durée mono (via get_next_action).
  • Reporté / lointain     → opacité réduite (dimmed).
Clic → sélection persistante + ouverture du panneau contextuel.
"""
from __future__ import annotations

import datetime
from nicegui import ui

_CSS = """
.str-row { display:flex; align-items:center; gap:12px; height:40px; padding:0 10px; border-radius:6px;
  cursor:pointer; color:var(--text); text-decoration:none;
  transition: background var(--duration-fast) var(--ease-standard); }
.str-row:hover { background:var(--surface); }
.str-row.selected { background:var(--surface); }
.str-row.dimmed { opacity:.55; }
.str-ring { font-size:14px; color:var(--text-muted); flex:0 0 16px; text-align:center; }
.str-id { font-family:var(--font-mono); font-size:11.5px; color:var(--text-muted); flex:0 0 46px; }
.str-main { flex:1 1 auto; min-width:0; display:flex; align-items:baseline; gap:8px; }
.str-title { font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.str-college { font-size:11.5px; color:var(--text-dim); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; flex:0 1 auto; }
.str-type { font-family:var(--font-mono); font-size:10px; letter-spacing:.03em; color:var(--text-muted);
  border:1px solid var(--border); border-radius:4px; padding:1px 5px; flex:0 0 auto; }
.str-dur { font-family:var(--font-mono); font-size:11.5px; color:var(--text-muted); flex:0 0 52px; text-align:right; }
.str-due { display:flex; align-items:center; gap:5px; flex:0 0 74px; font-size:11.5px; color:var(--text-muted); }
.str-due-dot { width:6px; height:6px; border-radius:50%; flex:0 0 6px; }
"""
_injected = {"done": False}


def _ring_glyph(score) -> str:
    """Anneau de progression (proxy sur le score de maîtrise — forme, pas couleur)."""
    if score is None:
        return "○"
    if score >= 95:
        return "●"
    if score >= 80:
        return "◉"
    if score >= 60:
        return "◕"
    if score >= 40:
        return "◑"
    if score >= 20:
        return "◔"
    return "○"


def type_tag(task) -> str:
    rt = task.review_type
    if rt == "qcm_error":
        return "QCM"
    if rt == "consolidation":
        return "CONSO"
    if rt == "lacune":
        return "LACUNE"
    if getattr(task, "has_pdf", False):
        return "PDF"
    return "NOTE"


def due_info(task) -> tuple[str, str]:
    """(couleur token, libellé) pour l'échéance selon urgence."""
    today = datetime.date.today()
    if task.days_overdue > 0:
        return "var(--danger)", f"−{task.days_overdue}j"
    due = task.due_date
    if due == today:
        return "var(--warning)", "auj."
    if due > today:
        delta = (due - today).days
        return "var(--success)", f"J-{delta}"
    return "var(--text-dim)", "—"


def ensure_styles() -> None:
    """Injecte le CSS du composant (à appeler au build synchrone de la page)."""
    if not _injected["done"]:
        ui.add_head_html(f"<style>{_CSS}</style>", shared=True)
        _injected["done"] = True


def study_task_row(task, *, selected: bool = False, on_select=None,
                   on_double_click=None, dimmed: bool = False) -> None:
    ensure_styles()

    from backend.core.reviews.recommendation_service import get_next_action
    dur = get_next_action(task).duration_min

    cls = "str-row"
    if selected:
        cls += " selected"
    if dimmed:
        cls += " dimmed"

    row = ui.element("div").classes(cls)
    if on_select is not None:
        row.on("click", lambda t=task: on_select(t))
    if on_double_click is not None:
        row.on("dblclick", lambda t=task: on_double_click(t))

    college = (task.college or [""])[0] if task.college else ""
    due_color, due_label = due_info(task)

    with row:
        ui.label(_ring_glyph(task.mastery_score)).classes("str-ring")
        ui.label(task.item_number or "—").classes("str-id")
        with ui.element("div").classes("str-main"):
            ui.label(task.course_title).classes("str-title")
            if college:
                ui.label(college).classes("str-college")
        ui.label(type_tag(task)).classes("str-type")
        ui.label(f"{dur} min").classes("str-dur")
        with ui.element("div").classes("str-due"):
            ui.element("span").classes("str-due-dot").style(f"background:{due_color}")
            ui.label(due_label)
