"""colleges_cockpit.py — Vue « Collèges » cockpit (refonte, session 7).

Vue principale de l'écran Collèges.
colleges.py). Liste dense, une ligne par collège : lus/total · barre de
progression · pourcentage · retard (cliquable) · fragiles · prochaine
révision · QCM moyen. Le chemin classic (grille de cartes + sélection +
grid de cours) reste strictement inchangé.

Écarts assumés (voir Journal du CLAUDE.md de la refonte) :
  • « retard » cliquable ouvre `/items?college=...` (README §5) — câblé pour
    de bon depuis la session 9 (Items) ;
  • « QCM moyen » = moyenne des *derniers* scores par cours
    (`get_qcm_last_scores_by_course`), pas une moyenne de toutes les
    sessions — aucun agrégat par collège n'existe côté backend, et c'est la
    même donnée « dernier score » déjà utilisée ailleurs (ex. dashboard_card) ;
  • « fragiles »/« prochaine rév. » dérivés d'un seul passage sur
    `review_service.generate_reviews("college")` déjà nécessaire pour
    « retard », plutôt que recalculer la mastery par cours un par un.
"""
from __future__ import annotations

from urllib.parse import quote

from nicegui import ui

from backend.state.store import data_store
from backend.state.catalog_repository import CatalogRepository
from backend.core.knowledge import store as knowledge_store
from backend.core.knowledge.college_validation import assess_college_validation
from backend.core.reviews import local_store
from backend.core.reviews.local_store import (
    get_all_history,
    get_qcm_last_scores_by_course,
)
from backend.core.reviews.validation import complete_review
from backend.core.reviews.service import build_review_types_by_course, review_service
from backend.core.reviews.reentry import filter_active_review_tasks, get_study_resume_date
from backend.core.prep.service import anchor_first_read
from backend.core.reviews.mastery import get_course_mastery, get_item_mastery
from backend.core.knowledge.item_progress import (
    is_item_started,
    scheduled_course_ids,
    validated_college_names,
    worked_course_ids,
)
from frontend.components.study_task_row import due_info
from frontend.components.mastery_indicator import (
    _LEVEL_COLOR,
    _level_from_score,
    provenance_tooltip,
)
from frontend.components.learning_metrics import build_advancement, college_progress_level
from frontend.components.data_grid import DataGrid, GridColumn
from frontend.components.status_badge import (
    STATUS_COLORS,
    STATUS_LABELS,
    STATUS_ORDER,
    status_class,
    status_label,
)
from frontend.components.ednpro_frequency_badge import ednpro_frequency_badge
from frontend.components.responsive_drawer import (
    responsive_drawer, close_drawer, open_drawer, ensure_styles as _drawer_styles,
)

_CSS = """
.cg-wrap { max-width:none; width:100%; }
.cg-layout { display:grid; grid-template-columns:minmax(0,1fr) 300px; gap:28px; align-items:start; width:100%; }
.cg-main { min-width:0; }
.cg-panel { border:1px solid var(--border); border-radius:10px; background:var(--surface); padding:16px; position:sticky; top:16px; }
.cg-panel-title { font-size:13px; font-weight:600; color:var(--text); }
.cg-panel-subtitle { font-size:11px; color:var(--text-muted); margin-top:3px; }
.cg-panel-section { margin-top:18px; }
.cg-panel-section-title { font-size:10px; text-transform:uppercase; letter-spacing:.06em; color:var(--text-dim); font-weight:600; margin-bottom:9px; }
.cg-kpis { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
.cg-kpi { padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--bg); }
.cg-kpi-value { font-family:var(--font-mono); font-size:18px; font-weight:600; color:var(--text); }
.cg-kpi-label { font-size:10px; color:var(--text-muted); margin-top:2px; }
.cg-kpi-sub { font-size:9.5px; color:var(--text-dim); margin-top:1px; }
.cg-progress-track { height:6px; border-radius:3px; background:var(--surface-hover); overflow:hidden; }
.cg-progress-fill { height:100%; border-radius:3px; background:var(--accent); }
.cg-priority { display:flex; align-items:center; gap:8px; padding:8px 0; border-bottom:1px solid var(--border); cursor:pointer; }
.cg-priority:last-child { border-bottom:none; }
.cg-priority:hover { color:var(--accent); }
.cg-priority-dot { width:7px; height:7px; border-radius:50%; flex:0 0 7px; }
.cg-priority-name { flex:1; min-width:0; font-size:11.5px; color:var(--text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.cg-priority-meta { font-size:10px; color:var(--text-muted); white-space:nowrap; }
.cg-mastery-row { display:flex; align-items:center; gap:8px; margin-top:7px; font-size:11px; color:var(--text-muted); }
.cg-mastery-row span:first-child { width:72px; }
.cg-mastery-row .cg-progress-track { flex:1; }
.cg-mastery-count { width:24px; text-align:right; font-family:var(--font-mono); font-size:10px; }
.cg-panel-action { width:100%; margin-top:8px; }
@media (max-width: 1100px) { .cg-layout { grid-template-columns:minmax(0,1fr) 260px; gap:18px; } }
@media (max-width: 820px) { .cg-layout { display:block; } .cg-panel { position:static; margin-top:24px; } }
.cg-topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; padding:4px 0 18px; flex-wrap:wrap; }
.cg-title { font-size:20px; font-weight:600; color:var(--text); letter-spacing:-0.01em; }
.cg-subtitle { font-size:12.5px; color:var(--text-muted); margin-top:4px; }
.cg-chips { display:flex; gap:6px; flex-wrap:wrap; }
.cg-chip { font-size:12px; font-weight:500; padding:5px 12px; border-radius:6px; cursor:pointer;
  color:var(--text-muted); border:1px solid var(--border); background:var(--bg);
  transition: background var(--duration-fast) var(--ease-standard),
              color var(--duration-fast) var(--ease-standard),
              border-color var(--duration-fast) var(--ease-standard); }
.cg-chip:hover { background:var(--surface); }
.cg-chip.active { background:var(--accent); border-color:var(--accent); color:var(--accent-text); }
.cg-head, .cg-row { display:grid; grid-template-columns:minmax(200px,2fr) minmax(120px,1fr) 42px 96px 90px 90px 52px; align-items:center; column-gap:14px; }
.cg-head > *, .cg-row > * { min-width:0; box-sizing:border-box; }
.cg-head { padding:0 12px 8px; font-size:10px;
  text-transform:uppercase; letter-spacing:.04em; color:var(--text-dim); font-weight:600;
  border-bottom:1px solid var(--border); }
.cg-h-name { flex:0 0 200px; }
.cg-h-bar { flex:1 1 auto; }
.cg-h-pct { flex:0 0 42px; text-align:right; }
.cg-h-retard { flex:0 0 96px; }
.cg-h-fragile { flex:0 0 90px; }
.cg-h-next { flex:0 0 90px; }
.cg-h-qcm { flex:0 0 52px; text-align:right; }
.cg-row { min-height:44px; padding:9px 12px;
  border-bottom:1px solid var(--border); transition: background var(--duration-fast) var(--ease-standard); }
.cg-row:hover { background:var(--surface-hover); }
.cg-row:last-child { border-bottom:none; }
.cg-name-cell { flex:0 0 200px; min-width:0; }
.cg-name { font-size:13.5px; font-weight:500; color:var(--text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.cg-name-sub { font-size:11px; color:var(--text-dim); margin-top:2px; }
.cg-bar-cell { flex:1 1 auto; }
.cg-bar-track { height:5px; border-radius:3px; background:var(--surface-hover); overflow:hidden; }
.cg-bar-fill { height:100%; border-radius:3px; transition: width var(--duration-base) var(--ease-standard); }
.cg-pct { flex:0 0 42px; text-align:right; font-family:var(--font-mono); font-size:12px; font-weight:600; color:var(--text); }
.cg-retard { flex:0 0 96px; display:flex; align-items:center; justify-content:space-between; gap:4px;
  padding:3px 8px; border-radius:6px; cursor:pointer; font-size:11.5px; }
.cg-retard.late { background:rgba(229,72,77,0.08); color:var(--danger-text); font-weight:500; }
.cg-retard.ok { color:var(--text-dim); }
.cg-unplanned { font-style:italic; }
.cg-resume { color:var(--warning-text); }
.cg-retard:hover { filter:brightness(0.97); }
.cg-fragile { flex:0 0 90px; display:flex; align-items:center; gap:6px; font-size:11.5px; color:var(--text-muted); }
.cg-fragile-dot { width:6px; height:6px; border-radius:50%; flex:0 0 6px; }
.cg-next { flex:0 0 90px; display:flex; align-items:center; gap:6px; font-size:11.5px; color:var(--text-muted); }
.cg-next-dot { width:6px; height:6px; border-radius:50%; flex:0 0 6px; }
.cg-qcm { flex:0 0 52px; text-align:right; font-family:var(--font-mono); font-size:12px; font-weight:600; }
.cg-empty { padding:32px 10px; text-align:center; color:var(--text-dim); font-size:13px; }
.cg-items { padding:8px 12px 12px 34px; background:var(--surface); border-bottom:1px solid var(--border); overflow-x:auto; }
@keyframes cgItemsEnter {
  0% { opacity: 0; transform: translateY(-8px); }
  100% { opacity: 1; transform: translateY(0); }
}
.cg-items-enter { animation: cgItemsEnter var(--duration-base) var(--ease-standard) both; }
.cg-context-open { display:none; color:var(--accent); cursor:pointer; font-size:12px; }
@media (min-width: 900px) and (max-width: 1199.98px) {
  .cg-layout { display:block; }
  .cg-panel { width:0; min-height:0; padding:0; border:0; }
  .cg-panel > .synapse-responsive-drawer { display:contents; }
  .cg-context-open { display:inline-flex; }
}
.cg-items-grid { min-width:880px; }
.cg-item-head, .cg-item { display:grid; grid-template-columns:minmax(180px,2fr) 76px 76px 120px 86px 100px 56px 104px 88px; align-items:center; column-gap:10px; }
.cg-item-head > *, .cg-item > * { min-width:0; box-sizing:border-box; }
.cg-item-head { min-height:24px; padding:0 0 5px; color:var(--text-dim); font-size:9px; font-weight:600; letter-spacing:.04em; text-transform:uppercase; }
.cg-item { min-height:36px; padding:5px 0; border-top:1px solid var(--border); }
.cg-item-title { min-width:0; font-size:12px; color:var(--text); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; cursor:pointer; }
.cg-item-cell { min-width:0; font-size:10.5px; color:var(--text-muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.cg-item-cell.center { text-align:center; }
.cg-item-cell.mono { font-family:var(--font-mono); font-size:11px; }
.cg-item-progress { display:flex; align-items:center; gap:6px; min-width:0; }
.cg-item-progress-track { flex:1; min-width:24px; height:5px; border-radius:3px; background:var(--surface-hover); overflow:hidden; }
.cg-item-progress-fill { height:100%; border-radius:3px; }
.cg-item-status { font-size:10px; font-weight:500; }
.cg-item-status.non-commence { color:var(--text-muted); }
.cg-item-status.a-lire { color:var(--text-muted); }
.cg-item-status.lu-sans-preuve { color:var(--warning-text); }
.cg-item-status.en-construction, .cg-item-status.a-consolider { color:var(--info); }
.cg-item-status.a-preparer, .cg-item-status.a-entrainer { color:var(--accent); }
.cg-item-status.correct { color:var(--text-muted); }
.cg-item-status.solide { color:var(--success-text); }
.cg-item-status.maitrise { color:var(--success-text); }
.cg-item-status.fragile { color:var(--warning-text); }
.cg-item-status.critique { color:var(--danger-text); }
.cg-item-late { color:var(--danger-text); font-weight:500; }
.cg-item-fragile { color:var(--warning-text); font-weight:500; }
.cg-item-muted { color:var(--text-muted); }
.cg-item-meta { font-size:10px; color:var(--text-muted); }
.cg-item-action { justify-self:end; }
.cg-item-empty { padding:20px 0; color:var(--text-muted); font-size:12px; }
@media (max-width: 820px) { .cg-items { padding-left:12px; } }
"""

_COLLEGE_ITEM_GRID = DataGrid(
    columns=(
        GridColumn("item", "Item", "minmax(180px,2fr)"),
        GridColumn("lecture", "Lecture", "76px"),
        GridColumn("mastery", "Maîtrise", "76px"),
        GridColumn("status", "Statut", "120px"),
        GridColumn("late", "Retard", "86px"),
        GridColumn("next", "Prochaine", "100px"),
        GridColumn("qcm", "QCM", "56px"),
        GridColumn("ednpro", "Priorité annale", "104px"),
        GridColumn("action", "", "88px"),
    )
)

_STOP_PROPAGATION_JS = "(event) => { event.stopPropagation(); emit(event); }"


def status_distribution_rows() -> list[tuple[str, str, str]]:
    """Return the single status vocabulary used by the pilotage panel."""
    return [
        (key, STATUS_LABELS[key], STATUS_COLORS.get(key, "var(--text-muted)"))
        for key in STATUS_ORDER
        if key in STATUS_LABELS
    ]


def count_no_pdf(courses: list) -> int:
    """Count fiches without a linked PDF, rather than colleges containing one."""
    return sum(1 for course in courses if not getattr(course, "url_pdf", None))


def _college_item_rows(
    courses: list,
    tasks: list,
    mastery_by_course: dict[str, tuple] | None = None,
    urgent_ids: set[str] | None = None,
    qcm_map: dict[str, dict] | None = None,
    frequency_map: dict[str, dict] | None = None,
    started_ids: set[str] | None = None,
    planned_ids: set[str] | None = None,
    missing_fiche_ids: set[str] | None = None,
) -> list[dict]:
    """Construit la vue simplifiée d'un collège, triée par numéro d'item.

    `started_ids` porte la réponse item par item : le fait qu'un item soit
    commencé ne dépend pas du collège déplié, sans quoi le même item s'affiche
    « critique » dans un collège et « À lire » dans un autre.
    """
    mastery_by_course = mastery_by_course or {}
    urgent_ids = urgent_ids or set()
    qcm_map = qcm_map or {}
    frequency_map = frequency_map or {}
    missing_fiche_ids = missing_fiche_ids or set()
    task_by_course: dict[str, object] = {}
    task_by_item: dict[str, object] = {}
    for task in tasks:
        previous = task_by_course.get(task.course_id)
        if previous is None or task.due_date < previous.due_date:
            task_by_course[task.course_id] = task
        item_number = str(getattr(task, "item_number", "") or "").strip()
        if item_number:
            previous_item = task_by_item.get(item_number)
            if previous_item is None or task.due_date < previous_item.due_date:
                task_by_item[item_number] = task

    def sort_key(course):
        raw = str(getattr(course, "item_number", "") or "")
        try:
            return (0, int(raw), str(getattr(course, "title", "")))
        except ValueError:
            return (1, raw, str(getattr(course, "title", "")))

    rows = []
    for course in sorted(courses, key=sort_key):
        item_number = str(getattr(course, "item_number", "") or "").strip()
        task = task_by_course.get(course.id) or task_by_item.get(item_number)
        mastery_values = tuple(mastery_by_course.get(course.id, (None, None)) or ())
        score = mastery_values[0] if mastery_values else None
        level = mastery_values[1] if len(mastery_values) > 1 else None
        evidence_count = mastery_values[2] if len(mastery_values) > 2 else 0
        semantics = _course_semantics(
            course, score, level,
            started=None if started_ids is None else str(course.id) in started_ids,
        )
        item_number = str(getattr(course, "item_number", "") or "").strip().removeprefix("ITEM ")
        rows.append({
            "course": course,
            "task": task,
            "pct": semantics["reading_pct"],
            "score": score,
            "evidence_count": evidence_count,
            **semantics,
            "missing_fiche": str(course.id) in missing_fiche_ids,
            "urgent": course.id in urgent_ids,
            "next_task": task,
            "qcm_score": qcm_map.get(course.id, {}).get("last_score"),
            "ednpro_frequency": frequency_map.get(item_number),
            "planned": bool(
                getattr(course, "date_1ere_lecture", None)
                or str(course.id) in (planned_ids or set())
            ),
        })
    return rows


def _course_semantics(
    course: object,
    score: int | None,
    level: str | None,
    started: bool | None = None,
) -> dict[str, object]:
    """Statut affiché d'un item. `started` est une propriété de l'item.

    Le statut vient intégralement de `level`, calculé une fois par
    `get_item_mastery` (mastery.py) : cette fonction ne fait plus que
    l'habiller pour la grille (libellé de lecture, pourcentage). Elle
    recalculait auparavant un statut indépendant à partir de `started` et de
    `score is None` — deux vocabulaires pour le même état, dont l'un dépendait
    du collège d'où l'item était regardé (72 items sur 175 changeaient de
    statut d'une ligne à l'autre, N10/N11).
    """
    if started is None:
        started = bool(getattr(course, "date_1ere_lecture", None))
    advancement = build_advancement(1 if started else 0, 1)
    status_key = level or "à préparer"
    return {
        "reading_pct": advancement["percent"] or 0,
        "lecture_label": "Lu" if started else "Non lu",
        "mastery_score": score,
        "level": level,
        "status_key": status_key,
        "status_text": status_label(status_key),
    }


def count_started(
    courses,
    active_course_ids: set[str],
    validated_colleges: set[str] | None = None,
) -> int:
    """Nombre d'items réellement entrés dans le travail.

    Le compte ne retenait que `date_1ere_lecture`, renseignée sur 8 fiches sur
    582, alors que 380 révisions avaient été effectuées — dont la plupart par
    des chemins (consolidation, bonus, annales) qui ne renseignent jamais ce
    champ. La progression affichait donc une inactivité qui n'existait pas.

    La règle vit désormais dans `is_item_started`, partagée avec le panneau de
    pilotage et la validation de collège : les trois comptaient différemment.
    """
    return sum(
        1
        for course in courses
        if is_item_started(course, active_course_ids, validated_colleges)
    )


def _pilotage_summary(rows: list[dict]) -> dict:
    """Agrégats légers pour le panneau de pilotage, sans nouvelle requête."""
    catalog_mode = any("item_ids" in row for row in rows)
    all_item_ids: set[str] = set()
    started_item_ids: set[str] = set()
    if catalog_mode:
        for row in rows:
            all_item_ids.update(str(item_id) for item_id in row.get("item_ids", set()))
            started_item_ids.update(str(item_id) for item_id in row.get("started_item_ids", set()))
    total_courses = len(all_item_ids) if catalog_mode else sum(r["total"] for r in rows)
    started = len(started_item_ids) if catalog_mode else sum(r["started"] for r in rows)
    status_counts: dict[str, int] = {}
    mastery_values: list[float] = []
    retention_values: list[float] = []
    # 132 des 133 scores affichés viennent d'une déclaration qui décroît avec
    # le temps, pas d'une mesure réelle (N04) : la moyenne agrégée doit dire
    # d'où elle vient, comme le fait déjà chaque ligne via `evidence_count`.
    mastery_declared = 0
    mastery_measured = 0
    # Deux espaces d'identifiants distincts : les statuts sont dédoublonnés par
    # item, les scores par fiche. Les mélanger faisait disparaître des statuts.
    seen_items: set[str] = set()
    seen_courses: set[str] = set()
    seen_retention_courses: set[str] = set()
    for row in rows:
        row_status_counts = row.get("status_counts", {})
        if catalog_mode and row.get("status_by_item"):
            row_status_counts = {
                status: sum(1 for item_id, item_status in row["status_by_item"].items()
                            if item_id not in seen_items and item_status == status)
                for status in set(row["status_by_item"].values())
            }
            seen_items.update(row["status_by_item"])
        for key, count in row_status_counts.items():
            status_counts[key] = status_counts.get(key, 0) + int(count)
        for course_id, value in row.get("mastery_by_course", {}).items():
            if course_id in seen_courses:
                continue
            seen_courses.add(course_id)
            score = value[0] if isinstance(value, tuple) else None
            if score is not None:
                mastery_values.append(float(score))
                evidence_count = value[2] if isinstance(value, tuple) and len(value) > 2 else 0
                if int(evidence_count or 0) > 0:
                    mastery_measured += 1
                else:
                    mastery_declared += 1
        for course_id, value in row.get("retention_by_course", {}).items():
            if course_id in seen_retention_courses:
                continue
            seen_retention_courses.add(course_id)
            if value is not None:
                retention_values.append(float(value))
    advancement = build_advancement(started, total_courses)
    no_pdf_course_ids: set[str] = set()
    # Un item multi-collèges comptait son retard/sa fragilité une fois par
    # collège où il apparaît (175 items concernés) : le panneau sommait donc
    # jusqu'à 246 « fragiles » pour 132 items réellement fragiles (N09). Comme
    # `no_pdf_course_ids` déjà déduplique par fiche, ces deux KPI dédupliquent
    # maintenant par item quand la ligne fournit l'ensemble ; à défaut (tests
    # historiques sans ces clés), on retombe sur la somme par collège.
    fragile_item_ids: set[str] = set()
    overdue_item_ids: set[str] = set()
    for row in rows:
        no_pdf_course_ids.update(str(course_id) for course_id in row.get("no_pdf_course_ids", set()))
        fragile_item_ids.update(str(item_id) for item_id in row.get("fragile_item_ids", set()))
        overdue_item_ids.update(str(item_id) for item_id in row.get("overdue_item_ids", set()))
    no_pdf_total = (
        len(no_pdf_course_ids)
        if no_pdf_course_ids
        else sum(int(r.get("no_pdf_count", r.get("no_pdf", False))) for r in rows)
    )
    fragile_total = len(fragile_item_ids) if fragile_item_ids else sum(r["fragile"] for r in rows)
    overdue_total = len(overdue_item_ids) if overdue_item_ids else sum(r["retard"] for r in rows)
    return {
        "total_courses": total_courses,
        "started": started,
        "pct": (advancement["percent"] / 100) if advancement["percent"] is not None else 0.0,
        "mastery_avg": round(sum(mastery_values) / len(mastery_values)) if mastery_values else None,
        "mastery_declared": mastery_declared,
        "mastery_measured": mastery_measured,
        "retention_avg": round(sum(retention_values) / len(retention_values)) if retention_values else None,
        "overdue": overdue_total,
        "fragile": fragile_total,
        "no_pdf": no_pdf_total,
        "status_counts": status_counts,
        "level_counts": status_counts,
        "estimated_minutes": max(0, total_courses - started) * 20,
    }


def render_colleges_cockpit() -> None:
    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)
    _drawer_styles()

    filt = {"unread": False, "overdue": False, "no_pdf": False}
    _meta: dict = {}
    expanded: set[str] = set()
    drawer_state: dict = {"root": None}

    with ui.column().classes("cg-wrap gap-0"):
        with ui.element("div").classes("cg-layout"):
            with ui.column().classes("cg-main gap-0"):
                topbar = ui.element("div").classes("cg-topbar")
                head = ui.element("div").classes("cg-head")
                list_col = ui.column().classes("w-full gap-0")
            panel = ui.element("aside").classes("cg-panel")
    with panel:
        def _close_context() -> None:
            if drawer_state["root"] is not None:
                close_drawer(drawer_state["root"])
        with responsive_drawer(on_close=_close_context, aria_label="Pilotage global") as drawer_root:
            drawer_state["root"] = drawer_root
            panel_content = ui.element("div")

    def _compute() -> list[dict]:
        history = get_all_history()
        college_statuses = knowledge_store.get_all_college_statuses()
        # Une seule lecture des deux signaux qui décident si un item est
        # commencé : la ligne, le panneau et la validation partagent la réponse.
        worked_ids = worked_course_ids()
        validated_colleges = validated_college_names(college_statuses)
        item_states = knowledge_store.get_all_item_states("college")
        generated = review_service.generate_reviews(context="college", active_only=False)
        resume_date = get_study_resume_date(data_store.preferences)
        all_tasks = filter_active_review_tasks(generated, resume_date)
        _meta["resume_date"] = resume_date
        _meta["hidden_tasks"] = len(generated) - len(all_tasks)
        planned_ids = scheduled_course_ids()
        tasks_by_course: dict[str, list] = {}
        for task in all_tasks:
            tasks_by_course.setdefault(str(task.course_id), []).append(task)
        history_by_course = build_review_types_by_course(history)
        urgent_ids = {t.course_id for t in review_service.get_urgent_tasks(all_tasks)}
        urgent_item_numbers = {
            str(t.item_number).strip()
            for t in all_tasks
            if t.course_id in urgent_ids and t.item_number
        }
        qcm_map = get_qcm_last_scores_by_course()
        frequency_map = local_store.get_all_ednpro_item_frequencies()
        catalog = CatalogRepository()
        catalog_item_rows = []
        if catalog.is_populated():
            from frontend.pages.items import build_item_rows
            catalog_item_rows = build_item_rows(catalog)
        # Items sans fiche (8, 10) : la ligne dépliée les affichait cliquables
        # vers `/cours/{id}` — une page morte, l'identifiant étant celui du
        # catalogue et non d'une fiche (N07).
        _meta["missing_fiche_ids"] = {
            str(row["item_id"]) for row in catalog_item_rows if row["missing_fiche"]
        }

        mastery_by_course: dict[str, tuple] = {}
        if catalog_item_rows:
            for item_row in catalog_item_rows:
                try:
                    snapshot = get_item_mastery(item_row["item_number"])
                except LookupError:
                    continue
                mastery_by_course[item_row["course"].id] = (
                    snapshot.score, snapshot.level, snapshot.evidence_count
                )
        else:
            snapshots_by_item: dict[str, object] = {}
            for candidate in data_store.cours:
                item_number = str(getattr(candidate, "item_number", "") or "").strip()
                if not item_number:
                    continue
                if item_number not in snapshots_by_item:
                    try:
                        snapshots_by_item[item_number] = get_item_mastery(item_number)
                    except LookupError:
                        snapshots_by_item[item_number] = get_course_mastery(candidate)
                snapshot = snapshots_by_item[item_number]
                mastery_by_course[candidate.id] = (
                    snapshot.score, snapshot.level, snapshot.evidence_count
                )

        # Preuve de consolidation au niveau item, annales et sessions IA
        # comprises — le même compte que `mastery.py` utilise pour son score
        # (N04). Sert à assouplir l'exigence de validation de collège (Q2) :
        # le cycle J3/J7/J14/J30 littéral n'était jamais atteint (0/44).
        consolidation_counts = {
            course_id: (value[2] if isinstance(value, tuple) and len(value) > 2 else 0)
            for course_id, value in mastery_by_course.items()
        }

        rows = []
        # `list_colleges_with_items()` exclut les collèges sans aucune relation
        # (un acronyme mal résolu à l'import crée une ligne fantôme — ex.
        # « Rhumatologie 🤝 », doublon vide de « Rhumatologie 🤲 », N05) : sans
        # ce filtre, `/colleges` affichait une ligne « 0/0 · À compléter ».
        college_names = (
            catalog.list_colleges_with_items() if catalog_item_rows else data_store.get_colleges()
        )
        for name in college_names:
            selected_item_rows = [row for row in catalog_item_rows if name in row["colleges"]]
            courses = (
                [row["course"] for row in selected_item_rows]
                if catalog_item_rows
                else data_store.get_cours_for_college(name)
            )
            ids = ({row["item_id"] for row in selected_item_rows}
                   if catalog_item_rows else {c.id for c in courses})
            total = len(ids)
            course_ids = {c.id for c in courses}
            validation = assess_college_validation(
                name,
                courses,
                item_states,
                history,
                manual_status=college_statuses.get(name, "non_etudie"),
                history_by_course=history_by_course,
                consolidation_counts=consolidation_counts,
            )
            # « Commencé » se décide item par item, avec la même règle que le
            # panneau : la ligne annonçait 257 items lus quand le panneau en
            # comptait 8.
            started_course_ids = {
                str(course.id) for course in courses
                if is_item_started(course, worked_ids, validated_colleges)
            }
            item_id_by_course = {
                str(row["course"].id): row["item_id"] for row in selected_item_rows
            }
            started_ids = {
                item_id_by_course.get(course_id, course_id)
                for course_id in started_course_ids
            }
            started = len(started_ids)
            advancement = build_advancement(started, total)
            pct = (advancement["percent"] / 100) if advancement["percent"] is not None else 0.0

            # Ensembles d'identifiants d'item, pas seulement des compteurs : un
            # item multi-collèges doit se dédupliquer au niveau du panneau
            # (N09), la ligne collège garde le compte local pour son propre
            # affichage.
            overdue_item_ids = (
                {str(row["item_id"]) for row in selected_item_rows
                 if str(row["item_number"]) in urgent_item_numbers}
                if catalog_item_rows else {cid for cid in ids if cid in urgent_ids}
            )
            retard_count = len(overdue_item_ids)
            fragile_item_ids = {
                item_id_by_course.get(str(course.id), str(course.id))
                for course in courses
                if mastery_by_course.get(course.id, (None, None))[1] in ("fragile", "critique")
            }
            fragile_count = len(fragile_item_ids)

            selected_item_numbers = {
                str(row["item_number"]).strip() for row in selected_item_rows
            }
            college_tasks = [
                task for task in all_tasks
                if (task.item_number and str(task.item_number).strip() in selected_item_numbers)
                or task.course_id in course_ids
            ]
            next_task = min(college_tasks, key=lambda t: t.due_date) if college_tasks else None

            qcm_scores = [
                qcm_map[cid]["last_score"] for cid in course_ids
                if cid in qcm_map and qcm_map[cid].get("last_score") is not None
            ]
            qcm_avg = round(sum(qcm_scores) / len(qcm_scores)) if qcm_scores else None

            no_pdf_count = count_no_pdf(courses)
            no_pdf = no_pdf_count > 0
            status_counts: dict[str, int] = {}
            status_by_item: dict[str, str] = {}
            for course in courses:
                score, level = mastery_by_course.get(course.id, (None, None))[:2]
                status_key = str(_course_semantics(
                    course, score, level, started=str(course.id) in started_course_ids
                )["status_key"])
                status_counts[status_key] = status_counts.get(status_key, 0) + 1
                item_key = item_id_by_course.get(str(course.id), course.id)
                status_by_item[item_key] = status_key
            retention_by_course = {
                cid: next(
                    (
                        getattr(task, "retention_score", None)
                        for task in tasks_by_course.get(str(cid), [])
                        if getattr(task, "retention_score", None) is not None
                    ),
                    None,
                )
                for cid in course_ids
            }

            rows.append({
                "name": name, "total": total, "started": started, "pct": pct,
                "retard": retard_count, "fragile": fragile_count,
                "overdue_item_ids": overdue_item_ids,
                "fragile_item_ids": fragile_item_ids,
                "next_task": next_task, "qcm_avg": qcm_avg, "unread": started == 0,
                "no_pdf": no_pdf,
                "no_pdf_count": no_pdf_count,
                "planned": sum(
                    1 for course in courses
                    if course.date_1ere_lecture or str(course.id) in planned_ids
                ),
                "planned_course_ids": {
                    str(course.id) for course in courses
                    if course.date_1ere_lecture or str(course.id) in planned_ids
                },
                "no_pdf_course_ids": {
                    str(course.id) for course in courses
                    if not getattr(course, "url_pdf", None)
                },
                "courses": courses,
                "tasks": college_tasks,
                "mastery_by_course": mastery_by_course,
                "retention_by_course": retention_by_course,
                "status_counts": status_counts,
                "urgent_ids": urgent_ids,
                "qcm_map": qcm_map,
                "frequency_map": frequency_map,
                "validation": validation,
                "item_ids": ids if catalog_item_rows else set(),
                "started_item_ids": started_ids if catalog_item_rows else set(),
                "started_course_ids": started_course_ids,
                "status_by_item": status_by_item,
            })
        return rows

    def _visible(rows: list[dict]) -> list[dict]:
        out = rows
        if filt["unread"]:
            out = [r for r in out if r["unread"]]
        if filt["overdue"]:
            out = [r for r in out if r["retard"] > 0]
        if filt["no_pdf"]:
            out = [r for r in out if r["no_pdf_count"] > 0]
        return out

    def _open_items(college: str) -> None:
        from urllib.parse import quote
        ui.navigate.to(f"/items?college={quote(college)}")

    def _start_item(course_id: str, title: str) -> None:
        """Ancre le cycle J1→J30 d'un item depuis la vue dépliée."""
        try:
            anchor_first_read(course_id)
        except Exception as exc:
            ui.notify(f"Planification impossible : {exc}", type="negative")
            return
        ui.notify(f"Cycle planifié · {title}", type="positive")
        _render(recompute=True)

    def _confirm_college(college: str) -> None:
        knowledge_store.set_college_status(college, "valide")
        ui.notify(f"Collège confirmé : {college}", type="positive")
        _render(recompute=True)

    def _draw_topbar(n_total: int) -> None:
        topbar.clear()
        with topbar:
            with ui.column().classes("gap-0"):
                ui.label("Collèges").classes("cg-title")
                ui.label(f"{n_total} collèges · Avancement par matière").classes("cg-subtitle")
                hidden = int(_meta.get("hidden_tasks") or 0)
                if hidden:
                    resume = _meta.get("resume_date")
                    ui.label(
                        f"Reprise le {resume:%d/%m} · {hidden} révision(s) antérieure(s) masquée(s)"
                    ).classes("cg-subtitle cg-resume")
            with ui.element("div").classes("cg-chips"):
                def _chip(label: str, key: str) -> None:
                    el = ui.element("div").classes("cg-chip active" if filt[key] else "cg-chip")
                    with el:
                        ui.label(label)
                    el.on("click", lambda k=key: _toggle(k))

                _chip("Jamais lus", "unread")
                _chip("En retard", "overdue")
                _chip("Sans PDF", "no_pdf")
            context = ui.label("Pilotage").classes("cg-context-open")
            context.on("click", lambda: open_drawer(drawer_state["root"]) if drawer_state["root"] else None)

    def _draw_pilotage(rows: list[dict]) -> None:
        panel_content.clear()
        summary = _pilotage_summary(rows)
        with panel_content:
            ui.label("Pilotage global").classes("cg-panel-title")
            ui.label("Les prochaines actions utiles").classes("cg-panel-subtitle")

            with ui.element("div").classes("cg-panel-section"):
                ui.label("Avancement de lecture").classes("cg-panel-section-title")
                with ui.row().classes("w-full items-end justify-between gap-2"):
                    ui.label(f"{int(summary['pct'] * 100)}%").classes("cg-kpi-value")
                    ui.label(f"{summary['started']} / {summary['total_courses']} cours lus").classes("cg-panel-subtitle")
                with ui.element("div").classes("cg-progress-track mt-2"):
                    ui.element("div").classes("cg-progress-fill").style(
                        f"width:{int(summary['pct'] * 100)}%"
                    )

            mastery_sub = None
            if summary["mastery_avg"] is not None:
                # 132 des 133 scores affichés viennent d'une déclaration, pas
                # d'une mesure (N04, N16) : la moyenne seule le cachait.
                mastery_sub = (
                    f"{summary['mastery_declared']} déclaré(s) · "
                    f"{summary['mastery_measured']} mesuré(s)"
                )
            with ui.element("div").classes("cg-kpis cg-panel-section"):
                for value, label, sub in [
                    (summary["overdue"], "révisions en retard", None),
                    (summary["fragile"], "items fragiles", None),
                    (summary["no_pdf"], "fiches sans PDF", None),
                    (f"{summary['estimated_minutes'] // 60} h", "charge estimée", None),
                    (f"{summary['mastery_avg']}%" if summary["mastery_avg"] is not None else "—", "maîtrise moyenne", mastery_sub),
                    (f"{summary['retention_avg']}%" if summary["retention_avg"] is not None else "—", "rétention", None),
                ]:
                    with ui.element("div").classes("cg-kpi"):
                        ui.label(str(value)).classes("cg-kpi-value")
                        ui.label(label).classes("cg-kpi-label")
                        if sub:
                            ui.label(sub).classes("cg-kpi-sub")

            with ui.element("div").classes("cg-panel-section"):
                ui.label("Répartition des statuts").classes("cg-panel-section-title")
                for key, label, color in status_distribution_rows():
                    count = summary["status_counts"].get(key, 0)
                    ratio = count / summary["total_courses"] if summary["total_courses"] else 0
                    with ui.element("div").classes("cg-mastery-row"):
                        ui.label(label)
                        with ui.element("div").classes("cg-progress-track"):
                            ui.element("div").style(
                                f"width:{int(ratio * 100)}%;background:{color}"
                            )
                        ui.label(str(count)).classes("cg-mastery-count")

            priorities = sorted(
                rows,
                key=lambda r: (-r["retard"], -r["fragile"], r["started"] == 0, r["pct"]),
            )[:3]
            with ui.element("div").classes("cg-panel-section"):
                ui.label("À traiter en priorité").classes("cg-panel-section-title")
                if not priorities:
                    ui.label("Aucun collège à afficher.").classes("cg-panel-subtitle")
                for row in priorities:
                    reason = (
                        f"{row['retard']} retard" if row["retard"]
                        else f"{row['fragile']} fragile" if row["fragile"]
                        else "à commencer"
                    )
                    priority = ui.element("div").classes("cg-priority")
                    with priority:
                        color = "var(--danger)" if row["retard"] else "var(--warning)" if row["fragile"] else "var(--text-dim)"
                        ui.element("span").classes("cg-priority-dot").style(f"background:{color}")
                        ui.label(row["name"]).classes("cg-priority-name")
                        ui.label(reason).classes("cg-priority-meta")
                    priority.on("click", lambda name=row["name"]: _open_items(name))

                ui.button("Voir les items prioritaires", icon="arrow_forward", on_click=lambda: ui.navigate.to("/items")).props(
                    "flat dense no-caps"
                ).classes("cg-panel-action")

    def _draw_head() -> None:
        head.clear()
        with head:
            ui.label("").classes("cg-h-name")
            ui.label("").classes("cg-h-bar")
            ui.label("%").classes("cg-h-pct")
            ui.label("RETARD").classes("cg-h-retard")
            ui.label("FRAGILES").classes("cg-h-fragile")
            ui.label("PROCHAINE").classes("cg-h-next")
            ui.label("QCM").classes("cg-h-qcm")

    def _draw_row(r: dict) -> None:
        pct_int = int(r["pct"] * 100)
        level = _level_from_score(pct_int if r["total"] else None)
        bar_color = _LEVEL_COLOR.get(level, "var(--text-muted)")
        restants = r["total"] - r["started"]

        row_el = ui.element("div").classes("cg-row cursor-pointer")
        row_el.on("click", lambda name=r["name"]: _toggle_expand(name))
        with row_el:
            with ui.element("div").classes("cg-name-cell"):
                ui.label(r["name"]).classes("cg-name")
                ui.label(f"{r['started']}/{r['total']} lus · {restants} restants").classes("cg-name-sub")
                validation = r["validation"]
                ui.label(validation.state_label).classes("cg-name-sub")
                evidence_count = validation.total_items - len(validation.missing_evidence_ids)
                cycle_count = len(validation.completed_j_cycle_ids)
                # « cycle J X/Y » se lisait comme un échec permanent — la
                # spirale J3/J7/J14/J30 littérale n'est presque jamais suivie
                # telle quelle (0/44 collèges) alors que la consolidation
                # réelle (annales, IA) existe et compte désormais (Q2).
                ui.label(
                    f"Preuves {evidence_count}/{validation.total_items} · "
                    f"consolidation {cycle_count}/{validation.total_items}"
                ).classes("cg-name-sub")
                if validation.manual_status != "valide":
                    action_label = "Confirmer" if validation.automatic_ready else "Valider manuellement"
                    confirm_button = ui.button(action_label, icon="check").props(
                        "flat dense no-caps size=sm color=primary"
                    )
                    confirm_button.on(
                        "click",
                        lambda name=r["name"]: _confirm_college(name),
                        js_handler=_STOP_PROPAGATION_JS,
                    )

            with ui.element("div").classes("cg-bar-cell"):
                with ui.element("div").classes("cg-bar-track"):
                    ui.element("div").classes("cg-bar-fill").style(
                        f"width:{pct_int}%; background:{bar_color}")

            progress_level = college_progress_level(
                pct_int,
                manually_validated=(
                    r["validation"].manual_status == "valide"
                    or r["validation"].automatic_ready
                ),
            )
            ui.label(f"{pct_int}%").classes("cg-pct").tooltip(progress_level)

            retard_cls = "cg-retard late" if r["retard"] > 0 else "cg-retard ok"
            retard_el = ui.element("div").classes(retard_cls)
            with retard_el:
                if r["retard"] > 0:
                    ui.label(f"{r['retard']} en retard")
                elif r.get("planned"):
                    ui.label("à jour")
                else:
                    # Aucune échéance parce qu'aucun cycle n'est posé : ce n'est
                    # pas la même chose qu'un collège à jour.
                    ui.label("non planifié").classes("cg-unplanned")
                ui.label("›")
            retard_el.on(
                "click",
                lambda name=r["name"]: _open_items(name),
                js_handler=_STOP_PROPAGATION_JS,
            )

            with ui.element("div").classes("cg-fragile"):
                dot_color = "var(--warning)" if r["fragile"] > 0 else "var(--text-dim)"
                ui.element("span").classes("cg-fragile-dot").style(f"background:{dot_color}")
                ui.label(f"{r['fragile']} fragiles")

            with ui.element("div").classes("cg-next"):
                nt = r["next_task"]
                if nt is None:
                    ui.label("—")
                else:
                    due_color, due_label = due_info(nt)
                    ui.element("span").classes("cg-next-dot").style(f"background:{due_color}")
                    ui.label(f"rév. {due_label}")

            qcm_avg = r["qcm_avg"]
            if qcm_avg is None:
                ui.label("—").classes("cg-qcm").style("color:var(--text-dim)")
            else:
                qcm_color = _LEVEL_COLOR.get(_level_from_score(qcm_avg), "var(--text-muted)")
                ui.label(f"{qcm_avg}%").classes("cg-qcm").style(f"color:{qcm_color}")

        if r["name"] in expanded:
            with ui.element("div").classes("cg-items cg-items-enter"):
                with ui.element("div").classes("cg-items-grid"):
                    with ui.element("div").classes("cg-item-head"):
                        for label in _COLLEGE_ITEM_GRID.labels:
                            ui.label(label)
                    item_rows = _college_item_rows(
                        r["courses"], r["tasks"], r["mastery_by_course"],
                        r["urgent_ids"], r["qcm_map"], r["frequency_map"],
                        started_ids=r.get("started_course_ids") or set(),
                        planned_ids=r.get("planned_course_ids") or set(),
                        missing_fiche_ids=_meta.get("missing_fiche_ids") or set(),
                    )
                    if not item_rows:
                        ui.label("Aucun item dans ce collège.").classes("cg-item-empty")
                    for item in item_rows:
                        course = item["course"]
                        task = item["task"]
                        with ui.element("div").classes("cg-item") as item_el:
                            number = getattr(course, "item_number", None) or "—"
                            title_text = f"Item {number} · {course.title}"
                            if item.get("missing_fiche"):
                                title_text += " · Fiche manquante"
                            title_el = ui.label(title_text).classes("cg-item-title")
                            if item.get("missing_fiche"):
                                # Pas de fiche dans le catalogue pour cet item :
                                # naviguer menait à une page « Item introuvable »
                                # (N07). Créer une fiche est une tâche de
                                # contenu, pas de code (Q5).
                                title_el.on(
                                    "click",
                                    lambda: ui.notify(
                                        "Aucune fiche pour cet item : à créer dans le catalogue.",
                                        type="warning",
                                    ),
                                )
                            else:
                                title_el.on(
                                    "click",
                                    lambda cid=course.id, name=r["name"]: ui.navigate.to(
                                        f"/cours/{cid}?college={quote(name)}"
                                    ),
                                )
                            ui.label(item["lecture_label"]).classes(
                                "cg-item-cell cg-item-lecture "
                                + ("text-emerald-400" if item["lecture_label"] == "Lu" else "cg-item-muted")
                            )

                            mastery_score = item["mastery_score"]
                            if mastery_score is None:
                                ui.label("—").classes("cg-item-cell cg-item-muted")
                            else:
                                mastery_color = _LEVEL_COLOR.get(
                                    _level_from_score(mastery_score), "var(--text-muted)"
                                )
                                mastery_label = ui.label(f"{mastery_score}%").classes(
                                    "cg-item-cell mono"
                                ).style(f"color:{mastery_color}")
                                mastery_label.tooltip(
                                    provenance_tooltip(item["evidence_count"])
                                )

                            ui.label(item["status_text"]).classes(
                                f"cg-item-cell cg-item-status {status_class(item['status_key'])}")

                            if item["urgent"]:
                                late = ui.label("En retard").classes("cg-item-cell cg-item-late")
                                late.on(
                                    "click",
                                    lambda name=r["name"]: _open_items(name),
                                    js_handler=_STOP_PROPAGATION_JS,
                                )
                            else:
                                ui.label("À jour").classes("cg-item-cell cg-item-muted")

                            next_task = item["next_task"]
                            if next_task is None:
                                ui.label("—").classes("cg-item-cell cg-item-muted")
                            else:
                                due_color, due_label = due_info(next_task)
                                with ui.row().classes("items-center gap-1 cg-item-cell"):
                                    ui.element("span").classes("cg-next-dot").style(f"background:{due_color}")
                                    ui.label(due_label)

                            qcm_score = item["qcm_score"]
                            if qcm_score is None:
                                ui.label("—").classes("cg-item-cell cg-item-muted")
                            else:
                                qcm_color = _LEVEL_COLOR.get(_level_from_score(qcm_score), "var(--text-muted)")
                                ui.label(f"{qcm_score}%").classes("cg-item-cell mono").style(f"color:{qcm_color}")

                            with ui.element("div").classes("cg-item-cell"):
                                ednpro_frequency_badge(item["ednpro_frequency"], compact=True)

                            if task is not None:
                                validate_button = ui.button("Valider", icon="check").props(
                                    "unelevated dense size=sm color=positive"
                                ).classes("cg-item-action")
                                validate_button.on(
                                    "click",
                                    lambda t=task, el=item_el: _open_feedback(t, el),
                                    js_handler=_STOP_PROPAGATION_JS,
                                )
                            elif item["planned"]:
                                ui.label("—").classes("cg-item-cell cg-item-muted cg-item-action")
                            else:
                                start_button = ui.button("Commencer", icon="play_arrow").props(
                                    "outline dense size=sm color=primary"
                                ).classes("cg-item-action")
                                start_button.tooltip(
                                    "Pose la première lecture aujourd'hui et planifie J1 → J30"
                                )
                                start_button.on(
                                    "click",
                                    lambda cid=course.id, t=course.title: _start_item(cid, t),
                                    js_handler=_STOP_PROPAGATION_JS,
                                )

    async def _validate(task, _card=None, activity_types=None, duration_minutes=None,
                        confidence=None, difficulty=None, qcm_result=None,
                        weak_category=None, weak_detail=None):
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
        ui.notify(f"✓ Validé : {task.course_title}", type="positive")
        _render(recompute=True)

    def _open_feedback(task, card) -> None:
        from frontend.pages.dashboard._dialogs import open_session_feedback_dialog
        open_session_feedback_dialog(task, card, _validate)

    def _toggle_expand(name: str) -> None:
        if name in expanded:
            expanded.remove(name)
        else:
            expanded.add(name)
        _draw_list(_computed_rows or [])

    def _draw_list(rows: list[dict]) -> None:
        list_col.clear()
        visible = _visible(rows)
        with list_col:
            if not visible:
                with ui.element("div").classes("cg-empty"):
                    ui.label("Aucun collège pour ce filtrage.")
                return
            for r in visible:
                _draw_row(r)

    def _toggle(key: str) -> None:
        filt[key] = not filt[key]
        _draw_topbar(len(_computed_rows or []))
        _draw_list(_computed_rows or [])

    _computed_rows: list[dict] | None = None

    def _render(*, recompute: bool = False) -> None:
        nonlocal _computed_rows
        if recompute or _computed_rows is None:
            _computed_rows = _compute()
        rows = _computed_rows
        _draw_topbar(len(rows))
        _draw_pilotage(rows)
        _draw_head()
        _draw_list(rows)

    _render(recompute=True)
