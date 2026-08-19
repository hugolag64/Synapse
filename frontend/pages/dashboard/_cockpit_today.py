"""_cockpit_today.py — Vue « Aujourd'hui » cockpit (refonte, session 3).

Vue principale de l'écran Aujourd'hui.
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
from backend.core.reviews.service import review_service, next_postpone_date
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
from frontend.components.responsive_drawer import (
    responsive_drawer, close_drawer, open_drawer, ensure_styles as _drawer_styles,
)
from frontend.pages.dashboard._dialogs import open_session_feedback_dialog
from frontend.components.flash_zero_cockpit import render_flash_zero_card, open_flash_zero_quiz
from frontend.components.course_prep_task_row import course_prep_task_row
from frontend.components.edn_insights_panel import render_edn_insights_panel
from backend.config.settings import business_today
from backend.core.edn.trajectory import build_progress_snapshot, project_to_exam, rank_gain_potential
from backend.core.practice.daily_queue import build_daily_question_queue, create_daily_queue_session
from backend.core.reviews.reentry import filter_post_resume_signals, get_study_resume_date
from backend.core.planning.sprint_countdown import SprintCountdownService

_DAYS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
_MONTHS_FR = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet",
              "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
_EDN_PRIORITY_WEIGHTS = {
    "indispensable": 1.0,
    "important": 0.75,
    "basique": 0.5,
    "jamais_tombe": 0.25,
}


def _gain_data_for_item(item_number: str) -> tuple[float, int, int | None]:
    frequency = local_store.get_ednpro_item_frequency(item_number) or {}
    priority = str(frequency.get("priority") or "basique").strip().lower()
    edn_weight = _EDN_PRIORITY_WEIGHTS.get(priority, 0.5)
    available_questions = len(
        local_store.get_ednpro_practice_questions(item_number, limit=1000) or []
    )
    raw_sessions = frequency.get("session_count")
    try:
        session_count = int(raw_sessions) if raw_sessions is not None else None
    except (TypeError, ValueError):
        session_count = None
    return edn_weight, available_questions, session_count

def build_gain_items(*, courses: list, tasks: list, error_signals: list[dict]) -> list[dict]:
    """Construit les priorités F3 à partir des données locales disponibles."""
    courses_by_item: dict[str, object] = {}
    for course in courses:
        item_number = str(getattr(course, "item_number", "") or "").strip()
        if item_number:
            courses_by_item.setdefault(item_number, course)

    tasks_by_item: dict[str, list] = {}
    for task in tasks:
        item_number = str(getattr(task, "item_number", "") or "").strip()
        if item_number:
            tasks_by_item.setdefault(item_number, []).append(task)

    error_counts: dict[str, int] = {}
    for signal in error_signals:
        item_number = str(signal.get("item_number", "") or "").strip()
        if item_number:
            error_counts[item_number] = error_counts.get(item_number, 0) + 1

    items = []
    for item_number, course in courses_by_item.items():
        item_tasks = tasks_by_item.get(item_number, [])
        scores = [
            float(task.mastery_score)
            for task in item_tasks
            if getattr(task, "mastery_score", None) is not None
        ]
        edn_weight, available_questions, frequency_sessions = _gain_data_for_item(item_number)
        item = {
            "item_number": item_number,
            "title": str(getattr(course, "title", "") or ""),
            "edn_weight": edn_weight,
            "mastery": sum(scores) / len(scores) if scores else 0,
            "error_count": error_counts.get(item_number, 0),
            "available_questions": available_questions,
            "estimated_minutes": 30,
        }
        if frequency_sessions is not None:
            item["frequency_sessions"] = frequency_sessions
        items.append(item)
    return rank_gain_potential(items=items)


_CSS = """
.cockpit-today { display:grid; grid-template-columns:minmax(0, 1fr) 8px var(--ct-panel-width,296px);
  gap:0; align-items:stretch; width:100%; box-sizing:border-box; }
.ct-center { min-width:0; max-width:none; }
.ct-resizer { flex:0 0 8px; width:8px; cursor:col-resize; position:relative; }
.ct-resizer::after { content:""; position:absolute; top:0; bottom:0; left:3px; width:1px; background:var(--border); }
.ct-resizer:hover::after { width:2px; left:2px; background:var(--accent); }
.ct-panel { width:100%; min-width:0; box-sizing:border-box; align-self:stretch; border-left:0;
  padding:8px 8px 16px 20px; min-height:calc(100vh - 60px); }
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
.ct-context-open { display:none; margin-left:auto; color:var(--accent); cursor:pointer; font-size:12px; }
@media (min-width: 900px) and (max-width: 1199.98px) {
  .cockpit-today { display:block; }
  .ct-resizer, .ct-panel-empty { display:none; }
  .ct-panel { width:0; min-height:0; padding:0; }
  .ct-context-open { display:block; }
  .ct-panel > .synapse-responsive-drawer { display:contents; }
}
@media (max-width: 767.98px) {
  .cockpit-today { display:flex; flex-direction:column; }
  .ct-center { max-width:none; width:100%; }
  .ct-resizer { display:none; }
  .ct-panel { width:100%; flex-basis:auto; margin:16px 0 0; padding:16px 0; border-top:1px solid var(--border); min-height:0; }
  .ct-qh-dur, .ct-qh-due { display:none; }
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
  const clamp = value => {
    const layoutWidth = layout.getBoundingClientRect().width;
    const maxWidth = Math.max(220, Math.min(520, layoutWidth - 360));
    return Math.max(220, Math.min(maxWidth, value));
  };
  const saved = Number(localStorage.getItem(key));
  if (saved) layout.style.setProperty('--ct-panel-width', `${clamp(saved)}px`);
  handle.addEventListener('pointerdown', event => {
    event.preventDefault();
    handle.setPointerCapture(event.pointerId);
    const move = moveEvent => {
      const layoutRect = layout.getBoundingClientRect();
      const width = clamp(layoutRect.right - moveEvent.clientX);
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
    _drawer_styles()

    state = DashboardState()
    sel: dict = {"task": None}
    drawer_state: dict = {"root": None}
    _data: dict = {"urgent": [], "today": [], "prep_tasks": [], "load": {}, "qcm": {}, "lac": {}, "crit": 0, "target": {}, "flash_zero": None, "flash_zero_dismissed": False, "flash_zero_complete": False, "edn_status": None, "edn_projections": (), "gain_items": (), "daily_queue": []}

    # ── Pipeline données (réplique de rebuild_all, partie data) ────────────────
    def _fetch() -> None:
        history = local_store.get_all_history()
        from backend.core.prep.store import list_prep_tasks
        prep_tasks = list_prep_tasks(business_today())
        all_tasks = review_service.generate_reviews(
            context=state.review_context,
            history=history,
            active_only=True,
        )
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

        targets = data_store.preferences.get("planning_targets", {})
        target = targets.get(datetime.date.today().isoformat(), {}) if isinstance(targets, dict) else {}
        budget = target.get("value", 0) if target.get("mode") == "minutes" else data_store.preferences.get("daily_budget_min", 0)
        load = compute_daily_load(urgent, today, heavy_threshold_min=budget if budget > 0 else 120)
        urgent, today, _overflow = apply_daily_budget(urgent, today, budget)
        if target.get("mode") == "items":
            today = today[:max(0, int(target.get("value", 0)) - len(urgent))]

        try:
            qcm = local_store.get_qcm_last_scores_by_course()
            lac = local_store.get_active_lacunes_count_by_course()
        except Exception:
            qcm, lac = {}, {}
        try:
            crit = local_store.get_critical_weak_points_count()
        except Exception:
            crit = 0

        timezone_name = data_store.preferences.get("timezone", "Europe/Paris")
        flash_zero = local_store.ensure_daily_flash_zero(business_today(), timezone_name=timezone_name)
        flash_zero_dismissed = local_store.is_daily_flash_zero_dismissed(business_today(), timezone_name=timezone_name)
        flash_zero_complete = local_store.is_daily_flash_zero_complete(business_today(), timezone_name=timezone_name)
        progress = build_progress_snapshot(
            courses=list(getattr(data_store, "cours", []) or []),
            tasks=all_tasks,
            history=history,
            as_of=business_today(),
        )
        countdown = SprintCountdownService(data_store.preferences.get("edn_target_date", "2026-10-15"))
        edn_status = countdown.get_sprint_status(today=business_today(), progress=progress)
        edn_projections = project_to_exam(
            progress,
            target_date=edn_status.target_date,
            daily_capacity_minutes=int(data_store.preferences.get("daily_budget_min", 60) or 60),
            today=business_today(),
        )
        try:
            error_signals = local_store.get_error_signals(days=30)
        except Exception:
            error_signals = []
        error_signals = filter_post_resume_signals(
            error_signals,
            get_study_resume_date(data_store.preferences),
        )
        gain_items = build_gain_items(
            courses=list(getattr(data_store, "cours", []) or []),
            tasks=all_tasks,
            error_signals=error_signals,
        )
        try:
            daily_queue = build_daily_question_queue(limit=5)
        except Exception:
            logger.exception("Impossible de construire la file des 5 questions du jour")
            daily_queue = []

        _data.update(urgent=urgent, today=today, prep_tasks=prep_tasks, load=load, qcm=qcm, lac=lac, crit=crit, target=target, flash_zero=flash_zero, flash_zero_dismissed=flash_zero_dismissed, flash_zero_complete=flash_zero_complete, edn_status=edn_status, edn_projections=edn_projections, gain_items=gain_items, daily_queue=daily_queue)

    # ── Focus (réutilise open_focus_mode existant) ────────────────────────────
    def _open_focus(task: ReviewTask | None = None) -> None:
        if task is not None:
            state.focus_tasks = [task] + [t for t in state.focus_tasks if t.id != task.id]
        open_focus_mode(state)

    def _open_daily_queue() -> None:
        session_id = create_daily_queue_session(limit=5)
        if session_id is None:
            ui.notify("Aucune question existante disponible aujourd'hui.", type="info")
            return
        from frontend.components.ai_practice_panel import _open_answer_dialog
        ui.notify("Les 5 questions du jour sont prêtes.", type="positive")
        _open_answer_dialog(session_id, _full_rebuild)

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

    def _open_feedback(task: ReviewTask) -> None:
        """Open the shared end-of-session self-evaluation before validation."""
        card = ui.element("div")
        card.set_visibility(False)
        open_session_feedback_dialog(task, card, validate_fn=_on_done)

    async def _on_postpone(task, card=None, days: int = 1) -> None:
        new_date = next_postpone_date(task.due_date, datetime.date.today(), days)
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

    def _open_prep_action(task) -> None:
        from frontend.components.course_quick_actions import open_course_prep_action
        open_course_prep_action(task, refresh_fn=_full_rebuild)

    def _validate_prep(task) -> None:
        from backend.core.prep.service import validate_prep_task
        try:
            validate_prep_task(task.id)
        except (KeyError, ValueError) as exc:
            ui.notify(str(exc), type="warning")
            return
        _full_rebuild()
        ui.notify(f"Préparation validée : ITEM {task.item_number}", type="positive")

    # ── Layout : conteneurs ───────────────────────────────────────────────────
    with ui.element("div").classes("cockpit-today"):
        center = ui.element("div").classes("ct-center")
        resizer = ui.element("div").classes("ct-resizer").props(
            'role="separator" aria-orientation="vertical" tabindex="0" '
            'aria-label="Redimensionner le panneau contexte"'
        )
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
            target = _data.get("target", {})
            if target.get("value"):
                ui.element("div").classes("ct-vsep")
                with ui.element("div").classes("ct-metric"):
                    ui.label(str(target["value"])).classes("ct-metric-strong")
                    ui.label("min objectif" if target.get("mode") == "minutes" else "items objectif").classes("ct-metric-sub")
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
                _context_open = ui.label("Contexte").classes("ct-context-open")
                _context_open.on("click", lambda: open_drawer(drawer_state["root"]) if drawer_state["root"] else None)
                with ui.element("div").classes("ct-toggle"):
                    ui.label("Jour").classes("ct-seg active")
                    ui.label("Semaine").classes("ct-seg").tooltip("Bientôt (vue Planning)")

            _render_summary(_data["load"], _data["crit"], total)

            if _data.get("edn_status") and data_store.preferences.get("edn_sprint_visible", True):
                render_edn_insights_panel(
                    _data["edn_status"],
                    _data["edn_projections"],
                    _data["gain_items"],
                    on_hide=_hide_sprint,
                )

            daily_queue = _data.get("daily_queue") or []
            if daily_queue:
                with ui.card().classes("w-full p-4 mb-4 border border-indigo-200 bg-indigo-50/40"):
                    with ui.row().classes("w-full items-center justify-between gap-3"):
                        with ui.column().classes("gap-1"):
                            ui.label("Les 5 du jour").classes("text-base font-semibold text-indigo-900")
                            items = ", ".join(
                                f"ITEM {row['item_number']}" for row in daily_queue
                            )
                            ui.label(
                                f"Questions déjà disponibles · {items or 'items non classés'}"
                            ).classes("text-xs text-indigo-700")
                        ui.button(
                            "Ouvrir la file", icon="school", on_click=_open_daily_queue
                        ).props("unelevated color=indigo")

            prep_tasks = _data.get("prep_tasks") or []
            if prep_tasks:
                with ui.card().classes("w-full p-4 mb-4 border border-amber-200 bg-amber-50/30"):
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label(f"Préparations FAC · {len(prep_tasks)}").classes(
                            "text-base font-semibold text-amber-900"
                        )
                        ui.label("À faire avant les cours à venir").classes(
                            "text-xs text-amber-700"
                        )
                    with ui.column().classes("w-full gap-2 mt-3"):
                        for prep_task in prep_tasks:
                            course_prep_task_row(
                                prep_task,
                                on_open=_open_prep_action,
                                on_validate=_validate_prep,
                            )

            def _finish_flash_zero() -> None:
                timezone_name = data_store.preferences.get("timezone", "Europe/Paris")
                local_store.complete_daily_flash_zero(business_today(), timezone_name=timezone_name)
                _full_rebuild()
                ui.notify("Flash-Zero terminé", type="positive")

            def _dismiss_flash_zero() -> None:
                timezone_name = data_store.preferences.get("timezone", "Europe/Paris")
                local_store.dismiss_daily_flash_zero(business_today(), timezone_name=timezone_name)
                _full_rebuild()
                ui.notify("Flash-Zero ignorÃ© pour aujourd'hui", type="info")

            if _data.get("flash_zero") and not _data.get("flash_zero_dismissed"):
                render_flash_zero_card(
                    _data["flash_zero"],
                    completed=_data["flash_zero_complete"],
                    on_open=lambda: open_flash_zero_quiz(on_complete=_finish_flash_zero),
                    on_dismiss=_dismiss_flash_zero,
                )

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
            def _close_context() -> None:
                if drawer_state["root"] is not None:
                    close_drawer(drawer_state["root"])

            with responsive_drawer(on_close=_close_context, include_close=False) as drawer_root:
                drawer_state["root"] = drawer_root
                if sel["task"] is not None:
                    context_panel(
                        sel["task"],
                        on_done=_open_feedback,
                        on_postpone=lambda t: _open_focus(t),
                        on_focus=lambda t: _open_focus(t),
                        on_close=_close_context,
                    )
                else:
                    with ui.element("div"):
                        ui.label("Contexte").classes("cp-label")
                        ui.label("Sélectionne une tâche pour voir le détail, la maîtrise et les ressources.").classes("ct-panel-empty")

    def _full_rebuild() -> None:
        _fetch()
        _render()

    def _hide_sprint() -> None:
        data_store.set_preference("edn_sprint_visible", False)
        _full_rebuild()
        ui.notify("Sprint masqué — réaffichable depuis les paramètres", type="info")

    state.rebuild_all = _full_rebuild

    # ── Chargement initial ────────────────────────────────────────────────────
    async def _load_all():
        _full_rebuild()

    ui.timer(0.05, _load_all, once=True)
