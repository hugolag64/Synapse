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

from nicegui import ui

from backend.state.store import data_store
from backend.core.reviews.local_store import get_all_history, get_qcm_last_scores_by_course
from backend.core.reviews.validation import complete_review
from backend.core.reviews.service import review_service
from frontend.components.study_task_row import due_info
from frontend.components.mastery_indicator import _LEVEL_COLOR, _level_from_score
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
.cg-head { display:flex; align-items:center; gap:14px; padding:0 12px 8px; font-size:10px;
  text-transform:uppercase; letter-spacing:.04em; color:var(--text-dim); font-weight:600;
  border-bottom:1px solid var(--border); }
.cg-h-name { flex:0 0 200px; }
.cg-h-bar { flex:1 1 auto; }
.cg-h-pct { flex:0 0 42px; text-align:right; }
.cg-h-retard { flex:0 0 96px; }
.cg-h-fragile { flex:0 0 90px; }
.cg-h-next { flex:0 0 90px; }
.cg-h-qcm { flex:0 0 52px; text-align:right; }
.cg-row { display:flex; align-items:center; gap:14px; min-height:44px; padding:9px 12px;
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
.cg-retard.late { background:rgba(229,72,77,0.08); color:var(--danger); font-weight:500; }
.cg-retard.ok { color:var(--text-dim); }
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
.cg-items-grid { min-width:760px; }
.cg-item-head, .cg-item { display:grid; grid-template-columns:minmax(180px,2fr) 76px 88px 86px 78px 100px 56px auto; align-items:center; column-gap:10px; }
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
.cg-item-status.correct { color:var(--text-muted); }
.cg-item-status.solide { color:var(--success); }
.cg-item-status.fragile { color:var(--warning); }
.cg-item-status.critique { color:var(--danger); }
.cg-item-late { color:var(--danger); font-weight:500; }
.cg-item-fragile { color:var(--warning); font-weight:500; }
.cg-item-muted { color:var(--text-muted); }
.cg-item-meta { font-size:10px; color:var(--text-muted); }
.cg-item-action { justify-self:end; }
.cg-item-empty { padding:20px 0; color:var(--text-muted); font-size:12px; }
@media (max-width: 820px) { .cg-items { padding-left:12px; } }
"""


def _college_item_rows(
    courses: list,
    tasks: list,
    mastery_by_course: dict[str, tuple] | None = None,
    urgent_ids: set[str] | None = None,
    qcm_map: dict[str, dict] | None = None,
) -> list[dict]:
    """Construit la vue simplifiée d'un collège, triée par numéro d'item."""
    mastery_by_course = mastery_by_course or {}
    urgent_ids = urgent_ids or set()
    qcm_map = qcm_map or {}
    task_by_course: dict[str, object] = {}
    for task in tasks:
        previous = task_by_course.get(task.course_id)
        if previous is None or task.due_date < previous.due_date:
            task_by_course[task.course_id] = task

    def sort_key(course):
        raw = str(getattr(course, "item_number", "") or "")
        try:
            return (0, int(raw), str(getattr(course, "title", "")))
        except ValueError:
            return (1, raw, str(getattr(course, "title", "")))

    rows = []
    for course in sorted(courses, key=sort_key):
        task = task_by_course.get(course.id)
        score, level = mastery_by_course.get(course.id, (None, None))
        started = bool(getattr(course, "date_1ere_lecture", None))
        if level is None:
            level = "correct" if started else "non_commence"
        rows.append({
            "course": course,
            "task": task,
            "pct": score if score is not None else (100 if started else 0),
            "score": score,
            "level": level,
            "urgent": course.id in urgent_ids,
            "next_task": task,
            "qcm_score": qcm_map.get(course.id, {}).get("last_score"),
        })
    return rows


def _pilotage_summary(rows: list[dict]) -> dict:
    """Agrégats légers pour le panneau de pilotage, sans nouvelle requête."""
    total_courses = sum(r["total"] for r in rows)
    started = sum(r["started"] for r in rows)
    level_counts = {"solide": 0, "correct": 0, "fragile": 0, "non_commence": 0}
    for row in rows:
        level = _level_from_score(int(row["pct"] * 100) if row["total"] else None)
        level_counts[level if level in level_counts else "non_commence"] += 1
    return {
        "total_courses": total_courses,
        "started": started,
        "pct": (started / total_courses) if total_courses else 0.0,
        "overdue": sum(r["retard"] for r in rows),
        "fragile": sum(r["fragile"] for r in rows),
        "no_pdf": sum(1 for r in rows if r["no_pdf"]),
        "level_counts": level_counts,
        "estimated_minutes": max(0, total_courses - started) * 20,
    }


def render_colleges_cockpit() -> None:
    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)
    _drawer_styles()

    filt = {"unread": False, "overdue": False, "no_pdf": False}
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
        all_tasks = review_service.generate_reviews(context="college", history=history)
        urgent_ids = {t.course_id for t in review_service.get_urgent_tasks(all_tasks)}
        qcm_map = get_qcm_last_scores_by_course()

        mastery_by_course: dict[str, tuple] = {}
        for t in all_tasks:
            mastery_by_course.setdefault(t.course_id, (t.mastery_score, t.mastery_level))

        rows = []
        for name in data_store.get_colleges():
            courses = data_store.get_cours_for_college(name)
            ids = {c.id for c in courses}
            total = len(courses)
            started = sum(1 for c in courses if c.date_1ere_lecture)
            pct = (started / total) if total else 0.0

            retard_count = sum(1 for cid in ids if cid in urgent_ids)
            fragile_count = sum(
                1 for cid in ids
                if mastery_by_course.get(cid, (None, None))[1] in ("fragile", "critique")
            )

            college_tasks = [t for t in all_tasks if t.course_id in ids]
            next_task = min(college_tasks, key=lambda t: t.due_date) if college_tasks else None

            qcm_scores = [
                qcm_map[cid]["last_score"] for cid in ids
                if cid in qcm_map and qcm_map[cid].get("last_score") is not None
            ]
            qcm_avg = round(sum(qcm_scores) / len(qcm_scores)) if qcm_scores else None

            no_pdf = any(not getattr(c, "url_pdf", None) for c in courses)

            rows.append({
                "name": name, "total": total, "started": started, "pct": pct,
                "retard": retard_count, "fragile": fragile_count,
                "next_task": next_task, "qcm_avg": qcm_avg, "unread": started == 0,
                "no_pdf": no_pdf, "courses": courses,
                "tasks": college_tasks,
                "mastery_by_course": mastery_by_course,
                "urgent_ids": urgent_ids,
                "qcm_map": qcm_map,
            })
        return rows

    def _visible(rows: list[dict]) -> list[dict]:
        out = rows
        if filt["unread"]:
            out = [r for r in out if r["unread"]]
        if filt["overdue"]:
            out = [r for r in out if r["retard"] > 0]
        if filt["no_pdf"]:
            out = [r for r in out if r["no_pdf"]]
        return out

    def _open_items(college: str) -> None:
        from urllib.parse import quote
        ui.navigate.to(f"/items?college={quote(college)}")

    def _draw_topbar(n_total: int) -> None:
        topbar.clear()
        with topbar:
            with ui.column().classes("gap-0"):
                ui.label("Collèges").classes("cg-title")
                ui.label(f"{n_total} collèges · progression par matière").classes("cg-subtitle")
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
                ui.label("Progression").classes("cg-panel-section-title")
                with ui.row().classes("w-full items-end justify-between gap-2"):
                    ui.label(f"{int(summary['pct'] * 100)}%").classes("cg-kpi-value")
                    ui.label(f"{summary['started']} / {summary['total_courses']} cours lus").classes("cg-panel-subtitle")
                with ui.element("div").classes("cg-progress-track mt-2"):
                    ui.element("div").classes("cg-progress-fill").style(
                        f"width:{int(summary['pct'] * 100)}%"
                    )

            with ui.element("div").classes("cg-kpis cg-panel-section"):
                for value, label in [
                    (summary["overdue"], "révisions en retard"),
                    (summary["fragile"], "collèges fragiles"),
                    (summary["no_pdf"], "sans PDF"),
                    (f"{summary['estimated_minutes'] // 60} h", "charge estimée"),
                ]:
                    with ui.element("div").classes("cg-kpi"):
                        ui.label(str(value)).classes("cg-kpi-value")
                        ui.label(label).classes("cg-kpi-label")

            with ui.element("div").classes("cg-panel-section"):
                ui.label("Répartition des collèges").classes("cg-panel-section-title")
                for key, label, color in [
                    ("solide", "Solides", "var(--success)"),
                    ("correct", "Corrects", "var(--info)"),
                    ("fragile", "Fragiles", "var(--warning)"),
                    ("non_commence", "Non commencés", "var(--text-dim)"),
                ]:
                    count = summary["level_counts"][key]
                    ratio = count / len(rows) if rows else 0
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

            with ui.element("div").classes("cg-bar-cell"):
                with ui.element("div").classes("cg-bar-track"):
                    ui.element("div").classes("cg-bar-fill").style(
                        f"width:{pct_int}%; background:{bar_color}")

            ui.label(f"{pct_int}%").classes("cg-pct")

            retard_cls = "cg-retard late" if r["retard"] > 0 else "cg-retard ok"
            retard_el = ui.element("div").classes(retard_cls)
            with retard_el:
                ui.label(f"{r['retard']} en retard" if r["retard"] > 0 else "à jour")
                ui.label("›")
            retard_el.on("click", lambda name=r["name"]: _open_items(name))

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
                        for label in ("Item", "Progression", "Statut", "Retard", "Fragile", "Prochaine", "QCM", ""):
                            ui.label(label)
                    item_rows = _college_item_rows(
                        r["courses"], r["tasks"], r["mastery_by_course"],
                        r["urgent_ids"], r["qcm_map"],
                    )
                if not item_rows:
                    ui.label("Aucun item dans ce collège.").classes("cg-item-empty")
                for item in item_rows:
                    course = item["course"]
                    task = item["task"]
                    with ui.element("div").classes("cg-item") as item_el:
                        number = getattr(course, "item_number", None) or "—"
                        title_el = ui.label(f"Item {number} · {course.title}").classes("cg-item-title")
                        title_el.on("click", lambda cid=course.id: ui.navigate.to(f"/cours/{cid}"))
                        with ui.element("div").classes("cg-item-progress"):
                            with ui.element("div").classes("cg-item-progress-track"):
                                ui.element("div").classes("cg-item-progress-fill").style(
                                    f"width:{max(0, min(100, item['pct']))}%;"
                                    f"background:{_LEVEL_COLOR.get(item['level'], 'var(--text-muted)')}"
                                )
                            ui.label(f"{item['pct']}%").classes("cg-item-cell mono")

                        status_label = {
                            "non_commence": "Non commencé",
                            "solide": "Solide",
                            "correct": "Correct",
                            "fragile": "Fragile",
                            "critique": "Critique",
                        }.get(item["level"], "—")
                        ui.label(status_label).classes(
                            f"cg-item-cell cg-item-status {item['level'].replace('_', '-')}")

                        if item["urgent"]:
                            late = ui.label("En retard").classes("cg-item-cell cg-item-late")
                            late.on("click", lambda name=r["name"]: _open_items(name))
                        else:
                            ui.label("À jour").classes("cg-item-cell cg-item-muted")

                        fragile = item["level"] in ("fragile", "critique")
                        ui.label("Oui" if fragile else "—").classes(
                            "cg-item-cell cg-item-fragile" if fragile else "cg-item-cell cg-item-muted")

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

                        if task is not None:
                            ui.button(
                                "Valider", icon="check",
                                on_click=lambda t=task, el=item_el: _open_feedback(t, el),
                            ).props("unelevated dense size=sm color=positive").classes("cg-item-action")
                        else:
                            ui.label("—").classes("cg-item-cell cg-item-muted cg-item-action")

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
        _render()

    def _open_feedback(task, card) -> None:
        from frontend.pages.dashboard._dialogs import open_session_feedback_dialog
        open_session_feedback_dialog(task, card, _validate)

    def _toggle_expand(name: str) -> None:
        if name in expanded:
            expanded.remove(name)
        else:
            expanded.add(name)
        _render()

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
        _render()

    def _render() -> None:
        rows = _compute()
        _draw_topbar(len(rows))
        _draw_pilotage(rows)
        _draw_head()
        _draw_list(rows)

    _render()
