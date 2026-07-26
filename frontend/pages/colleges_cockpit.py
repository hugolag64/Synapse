"""colleges_cockpit.py — Vue « Collèges » cockpit (refonte, session 7).

Rendu quand preferences['ui_mode'] == 'cockpit' (early-return depuis
colleges.py). Liste dense, une ligne par collège : lus/total · barre de
progression · pourcentage · retard (cliquable) · fragiles · prochaine
révision · QCM moyen. Le chemin classic (grille de cartes + sélection +
grid de cours) reste strictement inchangé.

Écarts assumés (voir Journal du CLAUDE.md de la refonte) :
  • « retard » cliquable doit ouvrir Items filtré sur ce collège (README §5) ;
    la vue Items n'existe pas encore (session 9) — toast « bientôt » en
    attendant, cohérent avec le badge « bientôt » déjà affiché dans la
    sidebar pour Items ;
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
from backend.core.reviews.service import review_service
from frontend.components.study_task_row import due_info
from frontend.components.mastery_indicator import _LEVEL_COLOR, _level_from_score

_CSS = """
.cg-wrap { max-width:1200px; width:100%; }
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
"""


def render_colleges_cockpit() -> None:
    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)

    filt = {"unread": False, "overdue": False, "no_pdf": False}

    with ui.column().classes("cg-wrap gap-0"):
        topbar = ui.element("div").classes("cg-topbar")
        head = ui.element("div").classes("cg-head")
        list_col = ui.column().classes("w-full gap-0")

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
                "no_pdf": no_pdf,
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
        ui.notify(f"Vue Items bientôt disponible (session 9) — {college}", type="info")

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

        with ui.element("div").classes("cg-row"):
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
        _draw_head()
        _draw_list(rows)

    _render()
