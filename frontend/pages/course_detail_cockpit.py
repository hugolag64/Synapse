"""course_detail_cockpit.py — Détail d'un item, vue cockpit (refonte, session 4).

Rendu quand preferences['ui_mode'] == 'cockpit' (early-return depuis
course_detail.py). Le chemin classic reste strictement inchangé, backend intact.

Structure (README § « 2. Détail d'un item ») :
  • en-tête synthétique : fil d'ariane · ITEM + titre + forme · méta (maîtrise,
    dernière révision, prochaine, QCM moyen) · actions ;
  • onglets Quasar : Vue d'ensemble · Note · Révisions · QCM · Lacunes · Historique ;
  • panneau droit 270px : Notions reliées · Rétroliens · Ressources.

Écarts assumés (voir Journal du CLAUDE.md de la refonte) :
  • la courbe d'oubli repose sur un modèle de présentation (cf. forgetting_curve) ;
  • la « série QCM adaptative » propose la série à partir des lacunes récurrentes
    réelles, mais son lancement route vers /qcm (pas de moteur de série côté backend).
"""
from __future__ import annotations

import asyncio
import datetime
import json

from nicegui import ui
from loguru import logger

from backend.state.store import data_store
from backend.core.reviews import local_store
from backend.core.reviews.mastery import get_course_mastery
from backend.core.reviews.anchors import anchor_priority, anchor_status, is_anchor_due
from backend.core.reviews.recommendation_service import get_next_action
from backend.core.reviews.service import review_service
from backend.core.reviews.models import ReviewTask
from backend.core.obsidian.service import obsidian_service
from backend.config.settings import settings as _settings

from frontend.components.mastery_indicator import (
    mastery_indicator, ensure_styles as _mastery_styles,
)
from frontend.components.forgetting_curve import (
    forgetting_curve, ensure_styles as _curve_styles,
)
from frontend.components.relation_graph import (
    relation_graph, neighbors_of, ensure_styles as _graph_styles,
)
from frontend.components.review_timeline import (
    review_timeline, build_stages, ensure_styles as _timeline_styles,
)
from frontend.components.oic_panel import (
    render_oic_panel, should_load_on_tab_activation,
)
from frontend.components.course_quick_actions import (
    _open_quick_qcm_dialog,
    open_pdf_wizard,
    open_start_tracking_dialog,
)
from frontend.components.anki_review_session import open_anki_review_session
from frontend.pages.dashboard._dialogs import open_session_feedback_dialog
from frontend.components.study_task_row import _ring_glyph

_MONTHS_FR = ["jan", "fév", "mar", "avr", "mai", "juin",
              "juil", "août", "sep", "oct", "nov", "déc"]

# Étape de workflow lisible depuis la forme de l'anneau (grammaire de statut).
_STAGE_LABEL = {
    "○": "À préparer", "◔": "À lire", "◑": "En construction",
    "◕": "À consolider", "◉": "À entraîner", "●": "Maîtrisé",
}

_CSS = """
.ci-wrap { display:flex; gap:0; align-items:flex-start; width:100%; }
.ci-center { flex:1 1 auto; min-width:0; max-width:900px; }
.ci-panel { flex:0 0 270px; width:270px; align-self:stretch; border-left:1px solid var(--border);
  padding:8px 8px 16px 20px; margin-left:24px; min-height:calc(100vh - 60px); }

.ci-crumb { display:flex; align-items:center; gap:6px; font-size:12px; color:var(--text-dim);
  height:34px; flex-wrap:wrap; }
.ci-crumb a { color:var(--text-dim); text-decoration:none; }
.ci-crumb a:hover { color:var(--text-muted); text-decoration:underline; }

.ci-head { display:flex; flex-wrap:wrap; align-items:baseline; gap:12px; }
.ci-head-id { font-family:var(--font-mono); font-size:12.5px; color:var(--text-muted); }
.ci-head-title { font-size:24px; font-weight:600; letter-spacing:-0.015em; color:var(--text);
  margin:0; line-height:1.2; }
.ci-head-stage { display:flex; align-items:center; gap:6px; font-size:12.5px; color:var(--text-muted); }

.ci-meta { display:flex; flex-wrap:wrap; align-items:center; gap:8px 18px; margin-top:12px;
  font-size:12.5px; color:var(--text-muted); }
.ci-meta-cell { display:flex; align-items:center; gap:8px; }
.ci-meta-label { color:var(--text-dim); }
.ci-meta-val { color:var(--text); }
.ci-meta-val.mono { font-family:var(--font-mono); }
.ci-dot { width:7px; height:7px; border-radius:50%; flex:0 0 7px; }

.ci-actions { display:flex; flex-wrap:wrap; gap:8px; margin:16px 0 4px; }
.ci-btn { display:inline-flex; align-items:center; gap:6px; height:32px; padding:0 14px;
  border-radius:6px; font-size:12.5px; font-weight:500; cursor:pointer; border:1px solid var(--border);
  background:var(--bg); color:var(--text) !important; text-decoration:none !important;
  transition: background var(--duration-fast) var(--ease-standard),
              border-color var(--duration-fast) var(--ease-standard); }
.ci-btn:hover { background:var(--surface); border-color:var(--border-strong); }
.ci-btn.primary { background:var(--accent); border-color:var(--accent); color:var(--accent-text) !important; }
.ci-btn.primary:hover { background:var(--accent-hover); }
.ci-btn.disabled { opacity:.45; cursor:default; }
.ci-btn.disabled:hover { background:var(--bg); border-color:var(--border); }

/* Onglets Quasar — souligné accent 2px, pas de ripple ni de majuscules */
.ci-tabs { border-bottom:1px solid var(--border); margin-top:18px; min-height:38px; }
.ci-tabs .q-tab { min-height:38px; padding:0 14px; text-transform:none; font-size:12.5px;
  font-weight:500; color:var(--text-muted); }
.ci-tabs .q-tab--active { color:var(--text); }
.ci-tabs .q-tab__indicator { height:2px; background:var(--accent); }
.ci-tabs .q-focus-helper, .ci-tabs .q-ripple { display:none !important; }
.ci-panels { background:transparent !important; }
.ci-panels .q-tab-panel { padding:18px 0 0; }
/* q-tab-panels est bâti sur q-carousel. Avec l'animation (défaut NiceGUI) le
   q-panel-parent prend une hauteur figée + overflow:hidden : l'onglet était
   clippé et le précédent restait visible. On construit donc les panneaux avec
   animated=False, et on laisse le contenu dicter la hauteur. Ne PAS forcer
   position:static ici : le carousel s'appuie dessus pour masquer les panneaux. */
.ci-panels .q-panel-parent { height:auto !important; overflow:visible !important; }

.ci-section { margin-bottom:22px; width:100%; }
.ci-label { font-size:10px; text-transform:uppercase; letter-spacing:.04em; color:var(--text-dim);
  font-weight:600; margin-bottom:8px; }
.ci-reco { background:var(--accent-wash); border-radius:8px; padding:14px 16px;
  width:100%; box-sizing:border-box; }
.ci-reco-meta { font-family:var(--font-mono); font-size:10.5px; letter-spacing:.04em;
  color:var(--text-muted); margin-bottom:8px; }
.ci-reco-body { font-size:14.5px; font-weight:600; color:var(--text); line-height:1.45; }
.ci-reco-sub { font-size:12.5px; color:var(--text-muted); margin-top:6px; line-height:1.5; }

.ci-grid2 { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:16px; }
@media (max-width: 900px) { .ci-grid2 { grid-template-columns:1fr; } }
.ci-card { border:1px solid var(--border); border-radius:8px; padding:14px; }
.ci-card-head { display:flex; align-items:baseline; justify-content:space-between; gap:8px; margin-bottom:10px; }
.ci-card-title { font-size:10px; text-transform:uppercase; letter-spacing:.04em;
  color:var(--text-dim); font-weight:600; }
.ci-card-sub { font-family:var(--font-mono); font-size:10.5px; color:var(--text-dim); }

.ci-prose { font-size:13px; line-height:1.65; color:var(--text-muted); }
.ci-note-perso { border-left:2px solid var(--accent); padding-left:12px; font-size:13px;
  line-height:1.6; color:var(--text-muted); }
.ci-empty { font-size:12.5px; color:var(--text-dim); padding:14px 0; }
.ci-path { font-family:var(--font-mono); font-size:10.5px; color:var(--text-dim);
  margin-bottom:12px; word-break:break-all; }

.ci-md { font-size:13.5px; line-height:1.7; color:var(--text); }
.ci-md h1, .ci-md h2, .ci-md h3 { font-weight:600; color:var(--text); margin:18px 0 8px; }
.ci-md h1 { font-size:17px; } .ci-md h2 { font-size:15px; } .ci-md h3 { font-size:13.5px; }
.ci-md p { margin:0 0 10px; } .ci-md ul, .ci-md ol { margin:0 0 10px 18px; }
.ci-md code { font-family:var(--font-mono); font-size:12px; background:var(--surface);
  border-radius:4px; padding:1px 4px; }
.ci-md a { color:var(--accent); text-decoration:none; }
.ci-md a:hover { text-decoration:underline; }

.ci-backlink { border:1px solid var(--border); border-radius:8px; padding:12px 14px; margin-top:16px; }
.ci-backlink-row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-top:8px; }
.ci-input { flex:1 1 220px; min-width:0; }
.ci-confirm { display:flex; align-items:center; gap:8px; font-size:12.5px;
  color:var(--text-muted); margin-top:8px; }

.ci-bar-row { display:flex; align-items:center; gap:12px; padding:6px 0; }
.ci-bar-label { font-size:12.5px; color:var(--text-muted); flex:0 0 130px; }
.ci-serie-chips { display:flex; flex-wrap:wrap; gap:6px; margin:10px 0 12px; }
.ci-chip { display:inline-flex; align-items:center; gap:6px; border:1px solid var(--border);
  border-radius:4px; padding:3px 8px; font-size:11.5px; color:var(--text-muted); background:var(--bg); }
.ci-chip .n { font-family:var(--font-mono); font-size:10.5px; color:var(--text-dim); }

.ci-lac { display:flex; align-items:flex-start; gap:10px; border:1px solid var(--border);
  border-radius:8px; padding:10px 12px; margin-bottom:8px; }
.ci-lac.resolved { opacity:.6; }
.ci-lac-body { flex:1 1 auto; min-width:0; }
.ci-lac-title { font-size:13px; color:var(--text); line-height:1.45; }
.ci-lac-sub { font-size:11.5px; color:var(--text-dim); margin-top:3px; }
.ci-lac-action { font-size:12px; color:var(--accent); cursor:pointer; flex:0 0 auto; }
.ci-lac-action:hover { text-decoration:underline; }

.ci-hist { display:flex; align-items:baseline; gap:12px; padding:7px 0; }
.ci-hist-date { font-family:var(--font-mono); font-size:11.5px; color:var(--text-dim); flex:0 0 60px; }
.ci-hist-badge { font-family:var(--font-mono); font-size:10px; background:var(--accent-wash);
  color:var(--text-muted); border-radius:4px; padding:2px 6px; flex:0 0 auto; }
.ci-hist-detail { font-size:12.5px; color:var(--text); flex:1 1 auto; min-width:0; }
.ci-hist-dur { font-family:var(--font-mono); font-size:11.5px; color:var(--text-dim); flex:0 0 auto; }

.ci-p-section { padding:14px 4px 0; }
.ci-p-link { display:flex; align-items:baseline; gap:6px; font-size:12.5px; color:var(--accent);
  text-decoration:none; padding:3px 0; cursor:pointer; }
.ci-p-link:hover { text-decoration:underline; }
.ci-p-link .n { font-family:var(--font-mono); font-size:10.5px; color:var(--text-dim);
  margin-left:auto; flex:0 0 auto; }
.ci-p-empty { font-size:12px; color:var(--text-dim); padding:2px 0; }
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_date(d) -> str:
    if d is None:
        return "—"
    if isinstance(d, str):
        try:
            d = datetime.date.fromisoformat(d[:10])
        except (ValueError, IndexError):
            return d[:10] or "—"
    if hasattr(d, "month"):
        base = f"{d.day} {_MONTHS_FR[d.month - 1]}"
        # L'année n'apparaît que si elle diffère de l'année courante, sinon un
        # événement de 2025 se lit comme une date à venir.
        return base if d.year == datetime.date.today().year else f"{base} {d.year}"
    return str(d)


def _rel_day(d) -> str:
    if isinstance(d, str):
        try:
            d = datetime.date.fromisoformat(d[:10])
        except (ValueError, IndexError):
            return "—"
    if not hasattr(d, "month"):
        return "—"
    delta = (datetime.date.today() - d).days
    if delta == 0:
        return "aujourd'hui"
    if delta == 1:
        return "hier"
    if 0 < delta < 7:
        return f"il y a {delta} j"
    return _fmt_date(d)


def _fmt_min(minutes) -> str:
    if not minutes:
        return ""
    m = int(minutes)
    if m >= 60:
        h, rem = divmod(m, 60)
        return f"{h}h{rem:02d}" if rem else f"{h}h"
    return f"{m} min"


def _urgency(due: datetime.date | None) -> str:
    if due is None:
        return "none"
    today = datetime.date.today()
    if due < today:
        return "late"
    if due == today:
        return "today"
    return "none"


def _urgency_color(urgency: str) -> str:
    return {"late": "var(--danger)", "today": "var(--warning)"}.get(urgency, "var(--success)")


def _row_get(row, key, default=None):
    """Accès tolérant aux sqlite3.Row comme aux dict."""
    try:
        val = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if val is None else val


# ── Page ──────────────────────────────────────────────────────────────────────

def render_item_cockpit(course_id: str) -> None:
    logger.info(f"ENTERING COURSE DETAIL (cockpit) — {course_id}")

    # CSS injecté AU BUILD synchrone (cf. Journal : un add_head_html tardif
    # n'atteint jamais le client).
    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)
    _mastery_styles()
    _curve_styles()
    _graph_styles()
    _timeline_styles()

    course = next((c for c in data_store.cours if c.id == course_id), None)
    if not course:
        with ui.element("div").classes("ci-center"):
            ui.label("Item introuvable.").classes("ci-empty")
            ui.link("‹ Retour à Aujourd'hui", "/").classes("ci-p-link")
        return

    # ── Données (mêmes sources que la vue classic) ────────────────────────────
    sessions = local_store.get_sessions_by_course().get(course_id, [])
    postpone_cnt = local_store.get_postpone_counts().get(course_id, 0)
    qcm_summary = local_store.get_qcm_summary_for_course(course_id)
    qcm_sessions = local_store.get_qcm_sessions_all(limit=20, course_id=course_id)
    lacunes = list(local_store.get_weak_points_for_course(course_id))
    review_hist = local_store.get_review_history_by_course(course_id)
    manual_reviews = local_store.get_manual_reviews_by_course(course_id)

    try:
        # Signature complète : (course, context, sessions, total_postpone, …).
        mastery = get_course_mastery(course, "college", sessions, postpone_cnt)
    except Exception as exc:
        logger.warning(f"mastery indisponible pour {course_id}: {exc}")
        mastery = None

    score = mastery.score if mastery else None
    level = mastery.level if mastery else None

    # Tâche de révision réelle si le moteur en produit une pour ce cours.
    # Deux sources, comme dans _cockpit_today._fetch : le moteur J3–J30 ET le
    # planificateur de consolidation. N'interroger que le premier faisait
    # afficher « non planifiée » sur un item que le dashboard donne en retard.
    task = None
    try:
        pending = review_service.generate_reviews(
            context="college", history=local_store.get_all_history()
        )
    except Exception as exc:
        logger.warning(f"generate_reviews indisponible pour {course_id}: {exc}")
        pending = []
    try:
        from backend.core.planning.service import planning_service
        cons, _ = planning_service.plan_consolidation()
        pending = list(pending) + list(cons)
    except Exception as exc:
        logger.warning(f"plan_consolidation indisponible pour {course_id}: {exc}")

    cands = [t for t in pending if t.course_id == course_id]
    task = min(cands, key=lambda t: t.due_date) if cands else None

    stages = build_stages(course, review_hist)
    next_stage = next((s for s in stages if s["state"] in ("late", "today", "future")), None)
    next_due = task.due_date if task else (next_stage["date"] if next_stage else None)
    next_cycle = task.review_type if task else (next_stage["cycle"] if next_stage else None)

    last_done = next(
        (_row_get(r, "completed_at") for r in review_hist if _row_get(r, "status") == "done"),
        None,
    )
    if not last_done and sessions:
        last_done = max((_row_get(s, "session_date", "") for s in sessions), default=None)

    # Ressources
    obs_configured = bool(_settings.obsidian_vault_path)
    obs_path = None
    if obs_configured:
        try:
            obs_path = obsidian_service.find_course_note(course)
        except Exception:
            obs_path = None
    has_pdf = bool(getattr(course, "url_pdf", None))

    item_label = course.display_item_number or course.item_number or "—"
    college = (course.college or [""])[0] if course.college else ""
    ring = _ring_glyph(score)
    item_key = str(course.display_item_number or course.item_number or "").strip()
    oic_course_ids = [
        c.id for c in data_store.cours
        if str(getattr(c, "display_item_number", "") or getattr(c, "item_number", "") or "").strip() == item_key
    ] or [course.id]

    # ── Focus : réutilise le Mode Focus existant ──────────────────────────────
    def _open_focus() -> None:
        if task is None:
            ui.notify("Aucune révision planifiée pour cet item.", type="info")
            return
        from frontend.pages.dashboard._state import DashboardState
        from frontend.pages.dashboard._reviews import open_focus_mode
        st = DashboardState()
        st.focus_tasks = [task]
        st.rebuild_all = lambda: ui.navigate.reload()
        open_focus_mode(st)

    # ── Layout ────────────────────────────────────────────────────────────────
    with ui.element("div").classes("ci-wrap"):
        center = ui.element("div").classes("ci-center")
        panel = ui.element("aside").classes("ci-panel")

    with center:
        # Fil d'ariane
        with ui.element("div").classes("ci-crumb"):
            ui.link("Aujourd'hui", "/")
            ui.label("›")
            if college:
                ui.link(college, "/colleges")
                ui.label("›")
            ui.label(f"Item {item_label}")

        # En-tête synthétique
        with ui.element("div").classes("ci-head"):
            ui.label(f"ITEM {item_label}").classes("ci-head-id")
            ui.label(course.title).classes("ci-head-title")
            with ui.element("div").classes("ci-head-stage"):
                ui.label(ring)
                ui.label(_STAGE_LABEL.get(ring, "À situer"))

        # Ligne de méta
        with ui.element("div").classes("ci-meta"):
            with ui.element("div").classes("ci-meta-cell"):
                ui.label("Maîtrise").classes("ci-meta-label")
                mastery_indicator(score, level, width="72px")
                ui.label(level or "à situer").classes("ci-meta-val")
            with ui.element("div").classes("ci-meta-cell"):
                ui.label("Dernière révision").classes("ci-meta-label")
                ui.label(_rel_day(last_done) if last_done else "jamais").classes("ci-meta-val")
            with ui.element("div").classes("ci-meta-cell"):
                ui.label("Prochaine").classes("ci-meta-label")
                urg = _urgency(next_due)
                ui.element("span").classes("ci-dot").style(f"background:{_urgency_color(urg)}")
                _next_txt = f"{next_cycle} · {_fmt_date(next_due)}" if next_cycle else "non planifiée"
                ui.label(_next_txt).classes("ci-meta-val mono")
            if qcm_summary.get("count"):
                with ui.element("div").classes("ci-meta-cell"):
                    ui.label("QCM moyen").classes("ci-meta-label")
                    ui.label(f"{qcm_summary['avg_score']} %").classes("ci-meta-val mono")

        # Actions
        with ui.element("div").classes("ci-actions"):
            _rev = ui.element("div").classes(
                "ci-btn primary" + ("" if task else " disabled")
            )
            with _rev:
                ui.label("Réviser maintenant")
            if task:
                _rev.on("click", _open_focus)
            else:
                _rev.tooltip("Aucune révision planifiée pour cet item")

            _anki = ui.element("div").classes("ci-btn")
            with _anki:
                ui.label("Réviser avec Anki")
            _anki.on(
                "click",
                lambda c=course: open_anki_review_session(
                    str(c.display_item_number or c.item_number or "") or None
                ),
            )

            if not has_pdf:
                _link_pdf = ui.element("div").classes("ci-btn warning")
                with _link_pdf:
                    ui.label("Lier un PDF")
                _link_pdf.on(
                    "click",
                    lambda c=course: open_pdf_wizard(
                        c, "college", lambda: ui.navigate.reload(), ui.context.client
                    ),
                )

            if has_pdf:
                ui.link("↗ PDF", f"/pdf/{course.id}", new_tab=True).classes("ci-btn")
            if obs_path is not None:
                _obs = ui.element("div").classes("ci-btn")
                with _obs:
                    ui.label("↗ Obsidian")
                _obs.on("click", lambda: obsidian_service.open_course_note(course))

        # ── Onglets ───────────────────────────────────────────────────────────
        with ui.tabs().props("no-caps align=left dense indicator-color=transparent").classes("ci-tabs") as tabs:
            t_over = ui.tab("Vue d'ensemble")
            t_note = ui.tab("Note")
            t_rev = ui.tab("Révisions")
            t_qcm = ui.tab("Entraînement")
            t_lac = ui.tab("Lacunes")
            t_oic = ui.tab("OIC")
            t_hist = ui.tab("Historique")

        oic_controller = None
        with ui.tab_panels(tabs, value=t_over, animated=False).classes("ci-panels w-full"):
            with ui.tab_panel(t_over):
                _tab_overview(course, task, score, level, next_due, next_cycle,
                              mastery, sessions)
            with ui.tab_panel(t_note):
                _tab_note(course, obs_path, obs_configured, item_label)
            with ui.tab_panel(t_rev):
                _tab_revisions(course, stages, manual_reviews, review_hist, _open_focus)
            with ui.tab_panel(t_qcm):
                _tab_qcm(course, qcm_summary, qcm_sessions, lacunes)
            with ui.tab_panel(t_lac):
                _tab_lacunes(lacunes)
            with ui.tab_panel(t_oic):
                oic_progress = ui.element("div").classes(
                    "px-5 py-3 flex items-center gap-6 flex-wrap border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/60"
                )
                oic_content = ui.element("div").classes("overflow-y-auto w-full")
                with oic_content:
                    ui.label("Ouvre cet onglet pour charger les OIC de l’item.").classes("ci-empty")
                oic_controller = render_oic_panel(
                    course,
                    oic_content,
                    oic_progress,
                    refresh_fn=lambda: ui.notify("État OIC mis à jour", type="positive"),
                    course_ids=oic_course_ids,
                    auto_load=False,
                )
            with ui.tab_panel(t_hist):
                _tab_history(sessions, qcm_sessions, lacunes, review_hist)

        async def _on_tab_change(event) -> None:
            active = getattr(event, "value", event)
            if oic_controller and should_load_on_tab_activation(active, oic_controller.loaded):
                await oic_controller.load()

        tabs.on_value_change(lambda event: asyncio.ensure_future(_on_tab_change(event)))

    with panel:
        _render_panel(course, lacunes, has_pdf, obs_path)


# ── Onglets ───────────────────────────────────────────────────────────────────

def _tab_overview(course, task, score, level, next_due, next_cycle,
                  mastery, sessions) -> None:
    # Bloc recommandation
    na = None
    if task is not None:
        try:
            na = get_next_action(task)
        except Exception as exc:
            logger.warning(f"get_next_action indisponible : {exc}")

    with ui.element("div").classes("ci-section"):
        with ui.element("div").classes("ci-reco"):
            ui.label("▸ CE QUE SYNAPSE RECOMMANDE").classes("ci-reco-meta")
            if na is not None:
                ui.label(na.label).classes("ci-reco-body")
                sub = []
                if na.reason:
                    sub.append(na.reason)
                if na.duration_min:
                    sub.append(f"~{na.duration_min} min")
                if sub:
                    ui.label(" — ".join(sub)).classes("ci-reco-sub")
            else:
                ui.label("Aucune révision planifiée pour cet item.").classes("ci-reco-body")
                ui.label(
                    "Il réapparaîtra dans la file dès que le moteur de répétition "
                    "espacée programmera une échéance."
                ).classes("ci-reco-sub")

    # Grille 2 colonnes : prédiction de maîtrise · notions reliées
    with ui.element("div").classes("ci-grid2 ci-section"):
        with ui.element("div").classes("ci-card"):
            with ui.element("div").classes("ci-card-head"):
                ui.label("Prédiction de maîtrise").classes("ci-card-title")
                ui.label("courbe d'oubli").classes("ci-card-sub")
            # Repère = jours restants avant l'échéance. Si elle est déjà passée,
            # un repère à J+1 n'apprend rien (et chevauche le point de départ) :
            # on projette alors sur un cycle complet.
            rtype = task.review_type if task else next_cycle
            remaining = (next_due - datetime.date.today()).days if next_due else None
            marker = remaining if (remaining or 0) >= 3 else None
            forgetting_curve(
                score,
                review_type=rtype,
                marker_days=marker,
                stability_days=mastery.retention_stability_days if mastery else None,
            )

        with ui.element("div").classes("ci-card"):
            neighbor_ids = neighbors_of(course.id)
            with ui.element("div").classes("ci-card-head"):
                ui.label("Notions reliées").classes("ci-card-title")
                ui.label(f"graphe · {len(neighbor_ids)} liens").classes("ci-card-sub")
            relation_graph(
                str(course.display_item_number or course.item_number or "?"),
                _neighbor_payload(neighbor_ids),
            )

    # Raisons du score + note perso
    if mastery is not None and mastery.reasons:
        with ui.element("div").classes("ci-section"):
            ui.label("Pourquoi ce score").classes("ci-label")
            ui.label(" · ".join(mastery.reasons[:4])).classes("ci-prose")

    # Note perso : le commentaire libre de la séance la plus récente qui en a un.
    recent = sorted(sessions, key=lambda s: str(_row_get(s, "session_date", "")), reverse=True)
    note = next((_row_get(s, "notes") for s in recent if _row_get(s, "notes")), None)
    if note:
        with ui.element("div").classes("ci-section"):
            ui.label("Note perso").classes("ci-label")
            ui.label(str(note)).classes("ci-note-perso")


def _neighbor_payload(neighbor_ids: list[str]) -> list[dict]:
    """Résout label / score / urgence des voisins depuis le store en mémoire."""
    out: list[dict] = []
    by_id = {c.id: c for c in data_store.cours}
    sessions_map = local_store.get_sessions_by_course()
    postpone_map = local_store.get_postpone_counts()

    for cid in neighbor_ids:
        c = by_id.get(cid)
        if c is None:
            continue
        try:
            m = get_course_mastery(c, "college", sessions_map.get(cid, []),
                                   postpone_map.get(cid, 0))
            nb_score = m.score
        except Exception:
            nb_score = None
        due = getattr(c, "lecture_j7_college", None)
        out.append({
            "label": c.title,
            "score": nb_score,
            "urgency": _urgency(due if isinstance(due, datetime.date) else None),
        })
    return out


def _tab_note(course, obs_path, obs_configured: bool, item_label: str) -> None:
    if not obs_configured:
        ui.label(
            "Aucun vault Obsidian configuré — renseigne le chemin dans Paramètres."
        ).classes("ci-empty")
        return

    if obs_path is None or not obs_path.exists():
        ui.label("Pas encore de note Obsidian pour cet item.").classes("ci-empty")

        async def _create():
            ok, res = await obsidian_service.create_course_note(course)
            if ok:
                ui.notify("Note créée ✓", type="positive")
                ui.navigate.reload()
            else:
                ui.notify(f"Erreur : {res}", type="negative")

        btn = ui.element("div").classes("ci-btn")
        with btn:
            ui.label("Créer la note")
        btn.on("click", lambda: asyncio.create_task(_create()))
        return

    ui.label(str(obs_path)).classes("ci-path")
    try:
        raw = obs_path.read_text(encoding="utf-8")
    except OSError as exc:
        ui.label(f"Note illisible : {exc}").classes("ci-empty")
        return

    # Frontmatter YAML retiré : c'est de la métadonnée, pas du contenu.
    body = raw
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) == 3:
            body = parts[2].lstrip("\n")

    ui.markdown(body).classes("ci-md")

    # ── Backlink vivant : sélection → lacune rattachée à l'item ───────────────
    with ui.element("div").classes("ci-backlink"):
        ui.label("Backlink vivant").classes("ci-label")
        ui.label(
            "Colle ou saisis le passage qui coince : il devient une lacune "
            "rattachée à cet item et entre dans la file de révision."
        ).classes("ci-prose")

        confirm = ui.element("div")

        with ui.element("div").classes("ci-backlink-row"):
            field = ui.input(placeholder="Ex. plaque stable vs instable").props(
                "dense outlined"
            ).classes("ci-input")

            def _create_lacune() -> None:
                detail = (field.value or "").strip()
                if not detail:
                    ui.notify("Saisis d'abord le passage à retenir.", type="warning")
                    return
                local_store.add_weak_point_full(
                    course_id=course.id,
                    detail=detail,
                    course_title=course.title,
                    item_number=str(course.item_number or ""),
                    severity=3,
                    source_type="obsidian",
                )
                field.value = ""
                confirm.clear()
                with confirm:
                    with ui.element("div").classes("ci-confirm"):
                        ui.element("span").classes("ci-dot").style("background:var(--success)")
                        ui.label(
                            f"Ajoutée à l'item {item_label} et à la file de révision."
                        )

            btn = ui.element("div").classes("ci-btn")
            with btn:
                ui.label("⚑ Créer une lacune")
            btn.on("click", _create_lacune)


def _tab_revisions(course, stages, manual_reviews, review_hist, on_planned_review) -> None:
    count = sum(1 for row in review_hist if _row_get(row, "status") == "done")
    with ui.row().classes("w-full items-center justify-between mb-4"):
        with ui.column().classes("gap-0"):
            ui.label("Cycle de révision").classes("ci-section-title")
            ui.label(f"{count} révision{'s' if count != 1 else ''} enregistrée{'s' if count != 1 else ''}").classes(
                "text-xs text-slate-400"
            )
        with ui.row().classes("gap-2"):
            add_btn = ui.element("div").classes("ci-btn primary")
            with add_btn:
                ui.label("Ajouter une révision")
            add_btn.on("click", lambda c=course: _open_manual_review_dialog(c))
            dates_btn = ui.element("div").classes("ci-btn")
            with dates_btn:
                ui.label("Modifier les dates")
            dates_btn.on(
                "click",
                lambda c=course: open_start_tracking_dialog(
                    c, "college", lambda: ui.navigate.reload(), ui.context.client, is_restart=True
                ),
            )

    review_timeline(stages, on_review=on_planned_review)

    if manual_reviews:
        ui.label("Révisions manuelles").classes("ci-section-title mt-5")
        for row in manual_reviews[:12]:
            date_txt = str(_row_get(row, "completed_at", "—"))[:10]
            confidence = _row_get(row, "confidence")
            difficulty = _row_get(row, "difficulty")
            meta = " · ".join(
                part for part in (
                    f"confiance {confidence}/5" if confidence else None,
                    difficulty,
                    f"{_row_get(row, 'notes')}" if _row_get(row, "notes") else None,
                ) if part
            )
            with ui.element("div").classes("ci-hist"):
                ui.label(_fmt_date(date_txt)).classes("ci-hist-date")
                ui.label("MANUELLE").classes("ci-hist-badge")
                ui.label(meta or "Révision enregistrée").classes("ci-hist-detail")


def _open_manual_review_dialog(course) -> None:
    today = datetime.date.today()
    task = ReviewTask(
        id=f"manual_{course.id}",
        course_id=course.id,
        course_title=course.title,
        item_number=str(course.display_item_number or course.item_number or "") or None,
        college=list(course.college or []),
        context="college",
        url_pdf=course.url_pdf,
        theoretical_due_date=today,
        due_date=today,
        review_type="manuel",
        nb_lectures=int(getattr(course, "nb_lectures", 0) or 0),
        qcm_done=bool(getattr(course, "qcm_done", False)),
    )

    async def _save_manual(_task, _card=None, activity_types=None,
                           duration_minutes=None, confidence=None,
                           difficulty=None, qcm_result=None,
                           weak_category=None, weak_detail=None,
                           session_date=None, **_kwargs):
        local_store.record_manual_review(
            course_id=course.id,
            course_title=course.title,
            item_number=str(course.display_item_number or course.item_number or ""),
            context="college",
            review_date=session_date or today,
            activity_types=activity_types or ["révision"],
            duration_minutes=duration_minutes,
            confidence=confidence,
            difficulty=difficulty,
            qcm_result=qcm_result,
            weak_category=weak_category,
            weak_detail=weak_detail,
        )
        ui.notify("Révision ajoutée à la timeline et à l’historique", type="positive")
        ui.navigate.reload()

    open_session_feedback_dialog(
        task,
        ui.element("div"),
        _save_manual,
        manual_date=today,
    )


def _tab_qcm(course, qcm_summary, qcm_sessions, lacunes) -> None:
    anki_btn = ui.element("div").classes("ci-btn")
    with anki_btn:
        ui.label("Réviser avec Anki")
    anki_btn.on("click", lambda c=course: open_anki_review_session(str(c.item_number or "") or None))

    btn = ui.element("div").classes("ci-btn primary")
    with btn:
        ui.label("Enregistrer un résultat")
    btn.on("click", lambda c=course: _open_quick_qcm_dialog(c, lambda: ui.navigate.reload()))

    if not qcm_summary.get("count"):
        ui.label("Aucune session QCM enregistrée pour cet item.").classes("ci-empty")
    else:
        last = qcm_summary.get("last_score")
        with ui.element("div").classes("ci-section"):
            for label, val in (("Dernier QCM", last), ("Moyenne", qcm_summary["avg_score"])):
                with ui.element("div").classes("ci-bar-row"):
                    ui.label(label).classes("ci-bar-label")
                    mastery_indicator(int(val) if val is not None else None)

    # Série adaptative : dérivée des lacunes récurrentes réelles
    active = [l for l in lacunes if (_row_get(l, "status", "") or "") != "résolue"]
    weighted = sorted(
        active,
        key=lambda l: (int(_row_get(l, "recurrence_count", 0) or 0),
                       int(_row_get(l, "severity", 2) or 2)),
        reverse=True,
    )[:3]

    with ui.element("div").classes("ci-reco"):
        ui.label("▸ SÉRIE QCM ADAPTATIVE").classes("ci-reco-meta")
        if not weighted:
            ui.label("Pas encore d'erreur récurrente à cibler.").classes("ci-reco-body")
            ui.label(
                "Enregistre des lacunes depuis l'onglet Note ou le mode focus "
                "pour que Synapse compose une série ciblée."
            ).classes("ci-reco-sub")
            return

        n_q = min(20, 5 * len(weighted))
        ui.label(
            f"{n_q} questions ciblées sur "
            f"{'ta lacune récurrente' if len(weighted) == 1 else f'tes {len(weighted)} erreurs récurrentes'}."
        ).classes("ci-reco-body")

        with ui.element("div").classes("ci-serie-chips"):
            for l in weighted:
                sev = int(_row_get(l, "severity", 2) or 2)
                color = ("var(--danger)" if sev >= 4
                         else "var(--warning)" if sev == 3 else "var(--text-dim)")
                rec = int(_row_get(l, "recurrence_count", 0) or 0)
                detail = str(_row_get(l, "detail", "") or "")[:44]
                with ui.element("div").classes("ci-chip"):
                    ui.element("span").classes("ci-dot").style(f"background:{color}")
                    ui.label(detail)
                    ui.label(f"×{max(1, rec)}").classes("n")

        btn = ui.element("div").classes("ci-btn primary")
        with btn:
            ui.label("Lancer la série adaptative")
        btn.on("click", lambda: ui.navigate.to("/qcm"))


def _tab_lacunes(lacunes) -> None:
    if not lacunes:
        ui.label("Aucune lacune enregistrée sur cet item.").classes("ci-empty")
        return

    anchors = [
        row for row in lacunes
        if anchor_status(row) == "actif"
    ]
    anchors.sort(key=lambda row: (-anchor_priority(row), not is_anchor_due(row)))
    if anchors:
        with ui.element("div").classes("ci-section ci-anchor-section"):
            with ui.element("div").classes("ci-card-head"):
                ui.label(f"⚓ ANCRAGES · {len(anchors)}").classes("ci-card-title")
                ui.label("erreurs persistantes à revoir jusqu’à résolution").classes("ci-card-sub")
            for anchor in anchors:
                due = is_anchor_due(anchor)
                with ui.element("div").classes("ci-lac ci-anchor" + (" due" if due else "")):
                    ui.element("span").classes("ci-dot").style(
                        f"background:{'var(--danger)' if due else 'var(--warning)'};margin-top:5px"
                    )
                    with ui.element("div").classes("ci-lac-body"):
                        ui.label(str(_row_get(anchor, "detail", "") or "—")).classes("ci-lac-title")
                        count = int(_row_get(anchor, "recurrence_count", 0) or 0)
                        ui.label(
                            f"Ancrage · {count} récurrence(s) · "
                            f"{'à revoir maintenant' if due else 'stable'}"
                        ).classes("ci-lac-sub")
                    if due:
                        act = ui.label("Marquer revu").classes("ci-lac-action")
                        act.on("click", lambda row=anchor: _review_anchor(row))

    for l in lacunes:
        status = str(_row_get(l, "status", "active") or "active")
        resolved = status == "résolue"
        sev = int(_row_get(l, "severity", 2) or 2)
        if resolved:
            color = "var(--success)"
        elif sev >= 4:
            color = "var(--danger)"
        elif sev == 3:
            color = "var(--warning)"
        else:
            color = "var(--text-dim)"

        with ui.element("div").classes("ci-lac" + (" resolved" if resolved else "")):
            ui.element("span").classes("ci-dot").style(f"background:{color};margin-top:5px")
            with ui.element("div").classes("ci-lac-body"):
                ui.label(str(_row_get(l, "detail", "") or "—")).classes("ci-lac-title")
                bits = []
                cat = _row_get(l, "category")
                if cat:
                    bits.append(str(cat))
                rec = int(_row_get(l, "recurrence_count", 0) or 0)
                if rec:
                    bits.append(f"revue {rec}×")
                bits.append(status)
                ui.label(" · ".join(bits)).classes("ci-lac-sub")
            if not resolved:
                act = ui.label("Revoir").classes("ci-lac-action")
                act.on("click", lambda: ui.navigate.to("/lacunes"))


def _review_anchor(row) -> None:
    """Repousse l'ancrage après un rappel volontaire."""
    weak_point_id = _row_get(row, "id")
    if weak_point_id is None:
        return
    local_store.mark_weak_point_reviewed(int(weak_point_id))
    ui.notify("Ancrage marqué comme revu", type="positive")
    ui.navigate.reload()


def _tab_history(sessions, qcm_sessions, lacunes, review_hist) -> None:
    events: list[dict] = []

    for s in sessions:
        d = str(_row_get(s, "session_date", "") or "")[:10]
        if not d:
            continue
        try:
            types = json.loads(_row_get(s, "activity_types", "") or "[]")
        except (ValueError, TypeError):
            types = []
        label = " + ".join(t.capitalize() for t in types[:2]) if types else "Séance"
        events.append({"date": d, "badge": "SÉANCE", "detail": label,
                       "dur": _fmt_min(_row_get(s, "duration_minutes"))})

    for q in qcm_sessions:
        d = str(_row_get(q, "session_date", "") or "")[:10]
        if not d:
            continue
        raw = _row_get(q, "score_raw") or (
            f"{_row_get(q, 'score_percent')} %" if _row_get(q, "score_percent") else "—"
        )
        events.append({"date": d, "badge": "QCM",
                       "detail": f"{raw} · {_row_get(q, 'platform', '?')}", "dur": ""})

    for l in lacunes:
        d = str(_row_get(l, "created_at", "") or "")[:10]
        if not d:
            continue
        events.append({"date": d, "badge": "LACUNE",
                       "detail": str(_row_get(l, "detail", "") or "")[:60], "dur": ""})

    for r in review_hist:
        if _row_get(r, "status") != "done":
            continue
        d = str(_row_get(r, "completed_at") or _row_get(r, "effective_due_date", "") or "")[:10]
        if not d:
            continue
        events.append({"date": d, "badge": "RÉVISION",
                       "detail": f"Cycle {_row_get(r, 'review_type', '—')}", "dur": ""})

    if not events:
        ui.label("Aucune activité enregistrée sur cet item.").classes("ci-empty")
        return

    events.sort(key=lambda e: e["date"], reverse=True)
    for ev in events[:25]:
        with ui.element("div").classes("ci-hist"):
            ui.label(_fmt_date(ev["date"])).classes("ci-hist-date")
            ui.label(ev["badge"]).classes("ci-hist-badge")
            ui.label(ev["detail"]).classes("ci-hist-detail")
            if ev["dur"]:
                ui.label(ev["dur"]).classes("ci-hist-dur")


# ── Panneau droit ─────────────────────────────────────────────────────────────

def _render_panel(course, lacunes, has_pdf: bool, obs_path) -> None:
    by_id = {c.id: c for c in data_store.cours}

    with ui.element("div").classes("ci-p-section"):
        ui.label("Notions reliées").classes("ci-label")
        neighbor_ids = neighbors_of(course.id)
        if not neighbor_ids:
            ui.label("— aucune").classes("ci-p-empty")
        for cid in neighbor_ids:
            c = by_id.get(cid)
            if c is None:
                continue
            link = ui.link(target=f"/cours/{cid}").classes("ci-p-link")
            with link:
                ui.label(f"◇ {c.title[:26]}")
                ui.label(str(c.display_item_number or c.item_number or "")).classes("n")

    with ui.element("div").classes("ci-p-section"):
        ui.label("Rétroliens").classes("ci-label")
        backlinks = [l for l in lacunes if _row_get(l, "obsidian_path")]
        if not backlinks:
            ui.label("— aucune note Obsidian ne pointe ici").classes("ci-p-empty")
        for l in backlinks[:6]:
            title = str(_row_get(l, "obsidian_title") or _row_get(l, "detail", "") or "")[:30]
            with ui.element("div").classes("ci-p-link"):
                ui.label(f"⚑ {title}")

    with ui.element("div").classes("ci-p-section"):
        ui.label("Ressources").classes("ci-label")
        any_res = False
        if has_pdf:
            ui.link("↗ PDF officiel", f"/pdf/{course.id}", new_tab=True).classes("ci-p-link")
            any_res = True
        if obs_path is not None:
            _o = ui.element("div").classes("ci-p-link")
            with _o:
                ui.label("↗ Note Obsidian")
            _o.on("click", lambda: obsidian_service.open_course_note(course))
            any_res = True
        fiche = getattr(course, "agregation_fiche_edn", None)
        if fiche:
            ui.link("↗ Fiche EDN", fiche, new_tab=True).classes("ci-p-link")
            any_res = True
        if not any_res:
            ui.label("— aucune ressource liée").classes("ci-p-empty")
