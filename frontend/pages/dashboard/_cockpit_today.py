"""_cockpit_today.py — Vue « Aujourd'hui » cockpit (refonte, session 3).

Rendu quand preferences['ui_mode'] == 'cockpit' (branché depuis __init__.py).
Réutilise le pipeline de données existant (review_service / recommendation_service)
et le Mode Focus existant (open_focus_mode) pour la validation.

Écart assumé (Journal) : les callbacks _on_done/_on_postpone/_on_ignore sont
copiés fidèlement depuis __init__.py plutôt que partagés — early-return isolé,
zéro risque pour l'UI classic. À dédupliquer quand classic sera retiré.
"""
from __future__ import annotations

import asyncio
import datetime

from nicegui import ui
from loguru import logger

from backend.core.notion.service import notion_service
from backend.core.reviews import local_store
from backend.core.reviews.service import review_service
from backend.core.reviews.models import ReviewTask
from backend.core.reviews.validation import complete_review
from backend.core.reviews.recommendation_service import (
    compute_daily_load, apply_daily_budget, get_next_action,
)
from backend.core.externat.service import externat_service
from backend.state.store import data_store

from ._state import DashboardState
from ._reviews import open_focus_mode
from frontend.components.study_task_row import (
    study_task_row, type_tag, due_info, ensure_styles as _row_styles,
)
from frontend.components.context_panel import (
    context_panel, ensure_styles as _panel_styles,
)
from frontend.components.mastery_indicator import ensure_styles as _mastery_styles

_DAYS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
_MONTHS_FR = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet",
              "Août", "Septembre", "Octobre", "Novembre", "Décembre"]

_CSS = """
.cockpit-today { display:flex; gap:0; align-items:stretch; width:100%; }
.ct-center { flex:1 1 auto; min-width:0; max-width:900px; }
.ct-resizer { flex:0 0 8px; width:8px; cursor:col-resize; position:relative; }
.ct-resizer::after { content:""; position:absolute; top:0; bottom:0; left:3px; width:1px; background:var(--border); }
.ct-resizer:hover::after { width:2px; left:2px; background:var(--accent); }
.ct-panel { flex:0 0 var(--ct-panel-width,296px); width:var(--ct-panel-width,296px); align-self:stretch; border-left:0;
  padding:8px 8px 16px 20px; margin-left:24px; min-height:calc(100vh - 60px); }
.ct-topbar { display:flex; align-items:center; gap:12px; height:46px; }
.ct-title { font-size:15px; font-weight:600; color:var(--text); }
.ct-date { font-size:12.5px; color:var(--text-dim); flex:1; }
.ct-toggle { display:flex; background:var(--surface); border-radius:6px; padding:2px; gap:2px; }
.ct-seg { font-size:12px; padding:3px 12px; border-radius:5px; color:var(--text-muted); cursor:pointer; }
.ct-seg.active { background:var(--bg); color:var(--text); font-weight:500; }
.ct-summary { display:flex; align-items:center; gap:16px; padding:12px 0; border-bottom:1px solid var(--border); flex-wrap:wrap; }
.ct-metric { display:flex; align-items:baseline; gap:6px; }
.ct-metric-strong { font-size:17px; font-weight:600; color:var(--text); }
.ct-metric-sub { font-size:12.5px; color:var(--text-muted); }
.ct-vsep { width:1px; height:16px; background:var(--border); }
.ct-dot { width:7px; height:7px; border-radius:50%; flex:0 0 7px; }
.ct-minibar { width:96px; height:5px; border-radius:3px; background:var(--surface-hover); overflow:hidden; margin-left:auto; }
.ct-minibar-fill { height:100%; background:var(--accent); border-radius:3px; }
.ct-reco { background:var(--accent-wash); border-radius:8px; padding:14px 16px; margin:16px 0; display:flex; gap:16px; align-items:flex-start; }
.ct-reco-body { flex:1; min-width:0; }
.ct-reco-meta { font-family:var(--font-mono); font-size:10.5px; letter-spacing:.04em; color:var(--text-muted);
  display:flex; align-items:center; gap:8px; margin-bottom:8px; }
.ct-reco-line { display:flex; align-items:baseline; gap:8px; }
.ct-reco-id { font-family:var(--font-mono); font-size:11.5px; color:var(--text-muted); flex:0 0 auto; }
.ct-reco-title { font-size:16px; font-weight:600; color:var(--text); }
.ct-reco-reason { font-size:12.5px; color:var(--text-muted); margin-top:6px; line-height:1.5; }
.ct-reco-sub { font-family:var(--font-mono); font-size:11px; color:var(--text-dim); margin-top:6px; }
.ct-tag { font-family:var(--font-mono); font-size:10px; color:var(--text-muted); border:1px solid var(--border);
  border-radius:4px; padding:2px 6px; flex:0 0 auto; }
.ct-reco-actions { display:flex; flex-direction:column; align-items:flex-end; gap:8px; flex:0 0 auto; }
.ct-btn-primary { background:var(--accent); color:var(--accent-text); border-radius:6px; padding:9px 16px;
  font-size:13px; font-weight:500; cursor:pointer; }
.ct-btn-primary:hover { background:var(--accent-hover); }
.ct-queue-head { display:flex; align-items:center; gap:12px; padding:10px 10px 6px; font-size:10px;
  text-transform:uppercase; letter-spacing:.04em; color:var(--text-dim); font-weight:600; }
.ct-qh-ring { flex:0 0 16px; }
.ct-qh-id { flex:0 0 46px; }
.ct-qh-main { flex:1 1 auto; }
.ct-qh-type { flex:0 0 auto; }
.ct-qh-dur { flex:0 0 52px; text-align:right; }
.ct-qh-due { flex:0 0 74px; }
.ct-empty { padding:24px 10px; color:var(--text-dim); font-size:13px; }
.ct-panel-empty { color:var(--text-dim); font-size:12.5px; padding:20px 4px; }
@media (max-width: 760px) {
  .cockpit-today { flex-direction:column; }
  .ct-center { max-width:none; width:100%; }
  .ct-resizer { display:none; }
  .ct-panel { width:100%; flex-basis:auto; margin:16px 0 0; padding:16px 0; border-top:1px solid var(--border); min-height:0; }
}
"""


def _clamp_panel_width(value: float, viewport_width: float) -> int:
    """Borne la largeur du panneau contexte pour préserver la file centrale."""
    max_width = max(220, min(520, int(viewport_width) - 360))
    return max(220, min(max_width, int(value)))


_RESIZER_JS = r"""
(() => {
  const key = 'synapse.dashboard.contextWidth';
  const layout = document.querySelector('.cockpit-today');
  const handle = layout?.querySelector('.ct-resizer');
  if (!layout || !handle || handle.dataset.ready) return;
  handle.dataset.ready = '1';
  const clamp = value => Math.max(220, Math.min(Math.min(520, innerWidth - 360), value));
  const saved = Number(localStorage.getItem(key));
  if (saved) layout.style.setProperty('--ct-panel-width', `${clamp(saved)}px`);
  handle.addEventListener('pointerdown', event => {
    event.preventDefault();
    handle.setPointerCapture(event.pointerId);
    const move = moveEvent => {
      const width = clamp(innerWidth - moveEvent.clientX - 24);
      layout.style.setProperty('--ct-panel-width', `${width}px`);
      localStorage.setItem(key, String(width));
    };
    const stop = () => {
      handle.removeEventListener('pointermove', move);
      handle.removeEventListener('pointerup', stop);
      handle.removeEventListener('pointercancel', stop);
    };
    handle.addEventListener('pointermove', move);
    handle.addEventListener('pointerup', stop);
    handle.addEventListener('pointercancel', stop);
  });
})();
"""


async def render_today_cockpit() -> None:
    logger.info("ENTERING DASHBOARD PAGE (cockpit today)")
    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)
    # CSS des composants injecté AU BUILD (sinon le lazy-inject arrive après
    # l'envoi de la page au client et le <style> n'atteint jamais le navigateur).
    _row_styles()
    _panel_styles()
    _mastery_styles()

    state = DashboardState()
    sel: dict = {"task": None}
    _data: dict = {"urgent": [], "today": [], "load": {}, "qcm": {}, "lac": {}, "crit": 0}

    # ── Pipeline données (réplique de rebuild_all, partie data) ────────────────
    def _fetch() -> None:
        history = local_store.get_all_history()
        all_tasks = review_service.generate_reviews(context=state.review_context, history=history)
        all_tasks = externat_service.apply_stage_boost(all_tasks)
        try:
            from backend.core.planning.service import planning_service
            cons, _ = planning_service.plan_consolidation()
            all_tasks = all_tasks + cons
        except Exception:
            pass

        urgent = review_service.get_urgent_tasks(all_tasks)
        today = review_service.get_today_tasks(all_tasks)
        state.focus_tasks = urgent + today

        budget = data_store.preferences.get("daily_budget_min", 0)
        load = compute_daily_load(urgent, today, heavy_threshold_min=budget if budget > 0 else 120)
        urgent, today, _overflow = apply_daily_budget(urgent, today, budget)

        try:
            qcm = local_store.get_qcm_last_scores_by_course()
            lac = local_store.get_active_lacunes_count_by_course()
        except Exception:
            qcm, lac = {}, {}
        try:
            crit = local_store.get_critical_weak_points_count()
        except Exception:
            crit = 0

        _data.update(urgent=urgent, today=today, load=load, qcm=qcm, lac=lac, crit=crit)

    # ── Focus (réutilise open_focus_mode existant) ────────────────────────────
    def _open_focus(task: ReviewTask | None = None) -> None:
        if task is not None:
            state.focus_tasks = [task] + [t for t in state.focus_tasks if t.id != task.id]
        open_focus_mode(state)

    # ── Callbacks validation (copie fidèle de __init__.py) ────────────────────
    async def _on_done(task, card=None, activity_types=None, duration_minutes=None,
                       confidence=None, difficulty=None, qcm_result=None,
                       weak_category=None, weak_detail=None) -> None:
        if task.review_type == "consolidation":
            complete_review(task, activity_types=activity_types, duration_minutes=duration_minutes,
                            confidence=confidence, difficulty=difficulty, qcm_result=qcm_result,
                            weak_category=weak_category, weak_detail=weak_detail)
        else:
            complete_review(task, activity_types=activity_types, duration_minutes=duration_minutes,
                            confidence=confidence, difficulty=difficulty, qcm_result=qcm_result,
                            weak_category=weak_category, weak_detail=weak_detail)
        state.done_today_count += 1
        if sel["task"] and sel["task"].id == task.id:
            sel["task"] = None
        _full_rebuild()
        ui.notify(f"✓ Révisé : {task.course_title}", type="positive")

        if task.review_type != "consolidation":
            async def _sync():
                c = next((x for x in data_store.cours if x.id == task.course_id), None)
                if not c:
                    return
                if task.context == "college":
                    ok = await notion_service.increment_lecture_college(c.id, c.nb_lectures)
                    if ok:
                        c.nb_lectures += 1
                else:
                    ok = await notion_service.increment_lecture_ue(c.id, c.nb_lectures_ue)
                    if ok:
                        c.nb_lectures += 1
                if ok:
                    data_store.save_to_disk()
            asyncio.create_task(_sync())

    async def _on_postpone(task, card=None, days: int = 1) -> None:
        new_date = task.due_date + datetime.timedelta(days=days)
        local_store.postpone(
            task_id=task.id, course_id=task.course_id, context=task.context,
            review_type=task.review_type, theoretical_due_date=task.theoretical_due_date,
            postponed_to=new_date, course_title=task.course_title,
            item_number=task.item_number or "",
        )
        if sel["task"] and sel["task"].id == task.id:
            sel["task"] = None
        _full_rebuild()
        ui.notify(f"Reporté au {new_date.strftime('%d/%m')} : {task.course_title}", type="info")

    async def _on_ignore(task, card=None) -> None:
        local_store.ignore(
            task_id=task.id, course_id=task.course_id, context=task.context,
            review_type=task.review_type, theoretical_due_date=task.theoretical_due_date,
            course_title=task.course_title, item_number=task.item_number or "",
        )
        if sel["task"] and sel["task"].id == task.id:
            sel["task"] = None
        _full_rebuild()
        ui.notify(f"Ignoré : {task.course_title}", type="warning")

    state._on_done = _on_done
    state._on_postpone = _on_postpone
    state._on_ignore = _on_ignore

    # ── Sélection ─────────────────────────────────────────────────────────────
    def _on_select(task) -> None:
        sel["task"] = task
        _render()

    def _open_item_detail(task) -> None:
        ui.navigate.to(f"/cours/{task.course_id}")

    # ── Layout : conteneurs ───────────────────────────────────────────────────
    with ui.element("div").classes("cockpit-today"):
        center = ui.element("div").classes("ct-center")
        resizer = ui.element("div").classes("ct-resizer").props('aria-label="Redimensionner le panneau contexte"')
        panel = ui.element("aside").classes("ct-panel")
    ui.timer(0.1, lambda: ui.run_javascript(_RESIZER_JS), once=True)

    # ── Rendu ─────────────────────────────────────────────────────────────────
    def _render_summary(load: dict, crit: int, total: int) -> None:
        with ui.element("div").classes("ct-summary"):
            h, m = load.get("estimated_h", 0), load.get("estimated_m", 0)
            time_txt = (f"{h} h {m:02d}" if h else f"{m} min")
            with ui.element("div").classes("ct-metric"):
                ui.label(time_txt).classes("ct-metric-strong")
                ui.label("recommandé").classes("ct-metric-sub")
            ui.element("div").classes("ct-vsep")
            with ui.element("div").classes("ct-metric"):
                ui.label(str(total)).classes("ct-metric-strong")
                ui.label("tâches").classes("ct-metric-sub")
            urgent_n = load.get("urgent_count", 0)
            if urgent_n:
                ui.element("div").classes("ct-vsep")
                with ui.element("div").classes("ct-metric"):
                    ui.element("span").classes("ct-dot").style("background:var(--danger)")
                    ui.label(f"{urgent_n} en retard").classes("ct-metric-sub")
            if crit:
                ui.element("div").classes("ct-vsep")
                with ui.element("div").classes("ct-metric"):
                    ui.element("span").classes("ct-dot").style("background:var(--warning)")
                    ui.label(
                        f"{crit} lacune{'s' if crit > 1 else ''} critique{'s' if crit > 1 else ''}"
                    ).classes("ct-metric-sub")
            # Mini-barre du jour
            done = state.done_today_count
            pct = int(done / (done + total) * 100) if (done + total) else 0
            with ui.element("div").classes("ct-minibar"):
                ui.element("div").classes("ct-minibar-fill").style(f"width:{pct}%")

    def _render_recommended(top) -> None:
        na = get_next_action(top)
        with ui.element("div").classes("ct-reco"):
            with ui.element("div").classes("ct-reco-body"):
                with ui.element("div").classes("ct-reco-meta"):
                    ui.label("▸ PROCHAINE ACTION")
                    if top.days_overdue > 0:
                        ui.element("span").classes("ct-dot").style("background:var(--danger)")
                        ui.label(f"Priorité haute · {top.type_badge} en retard {top.days_overdue} j")
                    else:
                        ui.element("span").classes("ct-dot").style("background:var(--warning)")
                        ui.label("Planifiée aujourd'hui")
                with ui.element("div").classes("ct-reco-line"):
                    ui.label(f"ITEM {top.item_number}" if top.item_number else "—").classes("ct-reco-id")
                    ui.label(top.course_title).classes("ct-reco-title")
                if na.reason:
                    ui.label(na.reason).classes("ct-reco-reason")
                _score = top.mastery_score if top.mastery_score is not None else "—"
                ui.label(f"~{na.duration_min} min · maîtrise {_score}").classes("ct-reco-sub")
            with ui.element("div").classes("ct-reco-actions"):
                ui.label(type_tag(top)).classes("ct-tag")
                _cta = ui.element("div").classes("ct-btn-primary")
                with _cta:
                    ui.label("Commencer")
                _cta.on("click", lambda t=top: _open_focus(t)).tooltip("Ouvrir en mode focus")

    def _render() -> None:
        center.clear()
        panel.clear()
        urgent, today = _data["urgent"], _data["today"]
        tasks = urgent + today
        total = len(tasks)

        with center:
            # Topbar
            now = datetime.datetime.now()
            with ui.element("div").classes("ct-topbar"):
                ui.label("Aujourd'hui").classes("ct-title")
                ui.label(f"{_DAYS_FR[now.weekday()]} {now.day} {_MONTHS_FR[now.month - 1]}").classes("ct-date")
                with ui.element("div").classes("ct-toggle"):
                    ui.label("Jour").classes("ct-seg active")
                    ui.label("Semaine").classes("ct-seg").tooltip("Bientôt (vue Planning)")

            _render_summary(_data["load"], _data["crit"], total)

            if tasks:
                _render_recommended(tasks[0])

                # File de travail
                with ui.element("div").classes("ct-queue-head"):
                    ui.label("").classes("ct-qh-ring")
                    ui.label("Item").classes("ct-qh-id")
                    ui.label(f"File de travail · {total}").classes("ct-qh-main")
                    ui.label("Type").classes("ct-qh-type")
                    ui.label("Durée").classes("ct-qh-dur")
                    ui.label("Échéance").classes("ct-qh-due")
                for t in tasks:
                    dimmed = (t.mastery_score is not None and t.mastery_score >= 80
                              and t.days_overdue <= 0)
                    is_sel = sel["task"] is not None and sel["task"].id == t.id
                    study_task_row(
                        t, selected=is_sel, on_select=_on_select,
                        on_double_click=_open_item_detail, dimmed=dimmed,
                    )
            else:
                ui.label("Rien à réviser aujourd'hui ✓").classes("ct-empty")

        with panel:
            if sel["task"] is not None:
                context_panel(
                    sel["task"],
                    on_done=lambda t: asyncio.create_task(_on_done(t)),
                    on_postpone=lambda t: _open_focus(t),
                    on_focus=lambda t: _open_focus(t),
                    on_close=lambda: (sel.update(task=None), _render()),
                )
            else:
                with ui.element("div"):
                    ui.label("Contexte").classes("cp-label")
                    ui.label("Sélectionne une tâche pour voir le détail, la maîtrise et les ressources.").classes("ct-panel-empty")

    def _full_rebuild() -> None:
        _fetch()
        _render()

    state.rebuild_all = _full_rebuild

    # ── Chargement initial ────────────────────────────────────────────────────
    async def _load_all():
        _full_rebuild()

    ui.timer(0.05, _load_all, once=True)
