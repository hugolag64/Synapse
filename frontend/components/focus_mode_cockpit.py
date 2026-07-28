"""focus_mode_cockpit.py — Mode focus plein écran cockpit (refonte, session 16).

`open_focus_mode()` (`frontend/pages/dashboard/_reviews.py`) est un dialog
partagé, appelé aussi bien depuis les pages classic (`dashboard_legacy.py`,
`dashboard/__init__.py`) que cockpit (`_cockpit_today.py`, `todo_cockpit.py`,
`course_detail_cockpit.py`). Impossible de le restyler sur place sans
casser le classic : `open_focus_mode` délègue donc désormais ici quand
`ui_mode == 'cockpit'`, sans toucher au rendu classic
(`render_review_card`) pour `ui_mode == 'classic'`.

Contrat conservé à l'identique (mêmes attributs `state` que le classic,
zéro changement côté appelants) : `state.focus_tasks`, `state.focus_cache`,
`state._on_done/_on_postpone/_on_ignore`, `state.rebuild_all`.

Écarts assumés (voir Journal du CLAUDE.md de la refonte) :
  • minuteur = vrai compte à rebours (le classic n'a qu'un chronomètre qui
    compte en avant) — démarre à `pomo_1_work` (Paramètres, 25 min par
    défaut), déjà une préférence existante, pas une valeur inventée ;
  • « Marquer terminé » ouvre `open_session_feedback_dialog` (confiance/
    difficulté/QCM), zéro dialog réimplémenté, comme partout ailleurs dans
    la refonte ; durée pré-remplie = minutes écoulées au minuteur si lancé ;
  • « Objectif » = `na.reason` (raison de `get_next_action`, déjà utilisée
    ailleurs) — aucun champ « objectif » libre n'existe côté backend ;
  • titre = `{na.label} — {task.course_title}` — approximation du titre
    narratif de la capture (« Consolider la note Athérome »), pas un champ
    littéral.
"""
from __future__ import annotations

from nicegui import ui

from backend.core.reviews.recommendation_service import get_next_action
from backend.state.store import data_store
from frontend.components.session_feedback import submit_session_feedback
from frontend.components.study_task_row import type_tag

_CSS = """
.fm-overlay { position:fixed; inset:0; background:var(--bg); z-index:2000; display:flex; flex-direction:column; }
.fm-header { display:flex; align-items:center; justify-content:space-between; height:52px; padding:0 20px;
  flex:0 0 auto; }
.fm-header-left { display:flex; align-items:center; gap:8px; }
.fm-logo { width:22px; height:22px; border-radius:6px; background:var(--accent); color:var(--accent-text);
  font-weight:600; font-size:12px; display:flex; align-items:center; justify-content:center; flex:0 0 22px; }
.fm-header-title { font-size:13px; color:var(--text-dim); font-weight:500; }
.fm-header-right { display:flex; align-items:center; gap:14px; }
.fm-pager { font-family:var(--font-mono); font-size:12px; color:var(--text-dim); }
.fm-quit { display:flex; align-items:center; gap:8px; font-size:13px; color:var(--text-muted); cursor:pointer; }
.fm-quit:hover { color:var(--text); }
.fm-quit kbd { font-family:var(--font-mono); font-size:10.5px; border:1px solid var(--border); border-radius:4px;
  padding:1px 5px; color:var(--text-dim); }
.fm-center { flex:1 1 auto; display:flex; flex-direction:column; align-items:center; justify-content:center;
  gap:10px; padding:24px; text-align:center; }
.fm-meta { font-family:var(--font-mono); font-size:11px; letter-spacing:.04em; color:var(--text-dim); }
.fm-title { font-size:30px; font-weight:600; color:var(--text); letter-spacing:-0.01em; max-width:640px; }
.fm-objectif { font-size:13.5px; color:var(--text-muted); max-width:520px; margin-bottom:10px; }
.fm-timer { font-family:var(--font-mono); font-size:68px; font-weight:600; color:var(--text); line-height:1;
  letter-spacing:-0.01em; margin-top:8px; }
.fm-timer.done { color:var(--danger); }
.fm-progress-track { width:220px; height:4px; border-radius:2px; background:var(--surface-hover); overflow:hidden; margin:14px 0 22px; }
.fm-progress-fill { height:100%; border-radius:2px; background:var(--accent); transition: width 1s linear; }
.fm-row { display:flex; align-items:center; gap:10px; }
.fm-row + .fm-row { margin-top:10px; }
.fm-btn { display:inline-flex; align-items:center; gap:7px; height:38px; padding:0 18px; border-radius:6px;
  font-size:13px; font-weight:500; cursor:pointer; border:1px solid var(--border); background:var(--bg);
  color:var(--text) !important; white-space:nowrap;
  transition: background var(--duration-fast) var(--ease-standard), border-color var(--duration-fast) var(--ease-standard); }
.fm-btn:hover { background:var(--surface); border-color:var(--border-strong); }
.fm-btn.primary { background:var(--accent); border-color:var(--accent); color:var(--accent-text) !important; }
.fm-btn.primary:hover { background:var(--accent-hover); }
"""


def open_focus_mode_cockpit(state) -> None:
    tasks = list(state.focus_tasks)
    if not tasks:
        ui.notify("Aucune révision à faire !", type="info")
        return

    # Le mode focus est ouvert après le chargement de la page (clic utilisateur).
    # add_head_html(shared=True) ne pousse pas toujours ce CSS au client déjà
    # connecté ; add_css l'envoie immédiatement dans la page active.
    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)
    ui.add_css(_CSS)

    _on_done = getattr(state, "_on_done", None)
    _on_postpone = getattr(state, "_on_postpone", None)
    _on_ignore = getattr(state, "_on_ignore", None)

    idx = {"i": 0}
    work_minutes = int(data_store.preferences.get("pomo_1_work", 25))
    timer_state = {"remaining": work_minutes * 60, "total": work_minutes * 60, "running": False}

    with ui.dialog(value=True).props("full-width full-height") as fdlg:  # noqa: SIM117
        with ui.element("div").classes("fm-overlay"):
            with ui.element("div").classes("fm-header"):
                with ui.element("div").classes("fm-header-left"):
                    ui.label("S").classes("fm-logo")
                    ui.label("Mode focus").classes("fm-header-title")
                with ui.element("div").classes("fm-header-right"):
                    pager = ui.label("").classes("fm-pager")
                    quit_btn = ui.element("div").classes("fm-quit")
                    with quit_btn:
                        ui.label("Quitter le focus")
                        ui.html("<kbd>esc</kbd>")
                    quit_btn.on("click", fdlg.close)
            center = ui.column().classes("fm-center")

    refs: dict = {}

    def _reset_timer() -> None:
        timer_state["remaining"] = work_minutes * 60
        timer_state["total"] = work_minutes * 60
        timer_state["running"] = False

    def _fmt_timer(seconds: int) -> str:
        m, s = divmod(max(0, seconds), 60)
        return f"{m:02d}:{s:02d}"

    def _render() -> None:
        center.clear()
        refs.clear()
        ticker.active = False
        t = tasks[idx["i"]]
        pager.set_text(f"{idx['i'] + 1} / {len(tasks)}" if len(tasks) > 1 else "")
        _reset_timer()

        na = get_next_action(t)
        college = (t.college or [""])[0] if t.college else ""

        with center:
            with ui.element("div").classes("fm-meta"):
                parts = [p for p in [
                    f"ITEM {t.item_number}" if t.item_number else None,
                    college.upper() if college else None,
                    type_tag(t),
                ] if p]
                ui.label(" · ".join(parts))

            ui.label(f"{na.label} — {t.course_title}").classes("fm-title")

            if na.reason:
                ui.label(f"Objectif : {na.reason}").classes("fm-objectif")

            refs["timer_lbl"] = ui.label(_fmt_timer(timer_state["remaining"])).classes("fm-timer")
            with ui.element("div").classes("fm-progress-track"):
                refs["progress_fill"] = ui.element("div").classes("fm-progress-fill").style("width:0%")

            with ui.element("div").classes("fm-row"):
                start_btn = ui.element("div").classes("fm-btn primary")
                with start_btn:
                    refs["start_lbl"] = ui.label("▶ Démarrer")
                start_btn.on("click", _toggle_timer)

                if t.has_pdf:
                    pdf_btn = ui.element("div").classes("fm-btn")
                    with pdf_btn:
                        ui.label("↗ Ouvrir PDF")
                    pdf_btn.on("click", lambda cid=t.course_id: ui.navigate.to(f"/pdf/{cid}", new_tab=True))

            with ui.element("div").classes("fm-row"):
                lac_btn = ui.element("div").classes("fm-btn")
                with lac_btn:
                    ui.label("⚑ Noter une lacune")
                lac_btn.on("click", lambda task=t: _note_lacune(task))

                done_btn = ui.element("div").classes("fm-btn")
                with done_btn:
                    ui.label("✓ Marquer terminé")
                done_btn.on("click", lambda task=t: _mark_done(task))

    def _toggle_timer() -> None:
        timer_state["running"] = not timer_state["running"]
        refs["start_lbl"].set_text("⏸ Pause" if timer_state["running"] else "▶ Reprendre")
        ticker.active = timer_state["running"]

    def _tick() -> None:
        if not timer_state["running"]:
            return
        timer_state["remaining"] = max(0, timer_state["remaining"] - 1)
        elapsed_pct = int((1 - timer_state["remaining"] / timer_state["total"]) * 100) if timer_state["total"] else 0
        refs["timer_lbl"].set_text(_fmt_timer(timer_state["remaining"]))
        refs["progress_fill"].style(f"width:{elapsed_pct}%")
        if timer_state["remaining"] <= 0:
            timer_state["running"] = False
            refs["timer_lbl"].classes(add="done")
            ticker.active = False

    ticker = ui.timer(1.0, _tick, active=False)

    def _elapsed_minutes() -> int | None:
        if timer_state["remaining"] == timer_state["total"]:
            return None
        return max(1, (timer_state["total"] - timer_state["remaining"]) // 60)

    def _note_lacune(task) -> None:
        from frontend.pages.dashboard._dialogs import open_lacune_inline_dialog
        open_lacune_inline_dialog(task, on_save=getattr(state, "rebuild_all", None))

    def _mark_done(task) -> None:
        from frontend.pages.dashboard._dialogs import open_session_feedback_dialog
        dummy_card = ui.element("div")
        dummy_card.set_visibility(False)
        open_session_feedback_dialog(
            task, dummy_card, _cockpit_on_done,
            initial_duration_minutes=_elapsed_minutes(),
        )

    async def _cockpit_on_done(
        task,
        card,
        activity_types=None,
        duration_minutes=None,
        confidence=None,
        difficulty=None,
        **feedback,
    ):
        await submit_session_feedback(
            _on_done,
            task,
            card,
            activity_types=activity_types,
            duration_minutes=duration_minutes,
            confidence=confidence,
            difficulty=difficulty,
            **feedback,
        )
        _nav(1)

    def _nav(delta: int) -> None:
        ni = idx["i"] + delta
        if 0 <= ni < len(tasks):
            idx["i"] = ni
            _render()
        elif ni >= len(tasks):
            ticker.active = False
            fdlg.close()
            ui.notify("✓ Focus terminé — toutes les révisions traitées !", type="positive")

    _render()
