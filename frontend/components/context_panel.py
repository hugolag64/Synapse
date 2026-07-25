"""context_panel — panneau contextuel droit de la vue Aujourd'hui (refonte).

En-tête (forme + titre court + id + ✕) puis sections :
  • Pourquoi maintenant (encadré accent-wash) — raison via get_next_action.
  • Maîtrise (barre + score).
  • Note Obsidian / Notions reliées — stubs (appartiennent au Détail item, session 4).
  • Ressources (PDF / Obsidian).
Pied : Terminer (primaire) / Reporter / Focus.
"""
from __future__ import annotations

from nicegui import ui

from frontend.components.mastery_indicator import mastery_indicator
from frontend.components.study_task_row import _ring_glyph, type_tag

_CSS = """
.cp { display:flex; flex-direction:column; gap:0; height:100%; }
.cp-head { display:flex; align-items:center; gap:8px; padding:0 4px 12px; border-bottom:1px solid var(--border); }
.cp-head-ring { font-size:14px; color:var(--text-muted); flex:0 0 auto; }
.cp-head-title { font-size:14px; font-weight:600; color:var(--text); flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.cp-head-id { font-family:var(--font-mono); font-size:11px; color:var(--text-dim); flex:0 0 auto; }
.cp-close { color:var(--text-dim); cursor:pointer; font-size:13px; flex:0 0 auto; line-height:1; }
.cp-section { padding:14px 4px 0; }
.cp-label { font-size:10px; text-transform:uppercase; letter-spacing:.04em; color:var(--text-dim); font-weight:600; margin-bottom:6px; }
.cp-why { background:var(--accent-wash); border-radius:6px; padding:10px 12px; font-size:12.5px; line-height:1.5; color:var(--text); }
.cp-stub { font-size:12px; color:var(--text-dim); font-style:normal; padding:2px 0; }
.cp-res { display:flex; align-items:center; gap:6px; font-size:12.5px; color:var(--accent); cursor:pointer; padding:3px 0; text-decoration:none; }
.cp-res:hover { text-decoration:underline; }
.cp-foot { margin-top:auto; padding-top:14px; display:flex; gap:8px; }
.cp-btn { flex:1; height:32px; border-radius:6px; font-size:12.5px; font-weight:500; cursor:pointer;
  display:flex; align-items:center; justify-content:center; border:1px solid var(--border);
  background:var(--bg); color:var(--text); transition: background var(--duration-fast) var(--ease-standard); }
.cp-btn:hover { background:var(--surface); }
.cp-btn.primary { background:var(--accent); color:var(--accent-text); border-color:var(--accent); }
.cp-btn.primary:hover { background:var(--accent-hover); }
"""
_injected = {"done": False}


def ensure_styles() -> None:
    """Injecte le CSS du composant (à appeler au build synchrone de la page)."""
    if not _injected["done"]:
        ui.add_head_html(f"<style>{_CSS}</style>", shared=True)
        _injected["done"] = True


def context_panel(task, *, on_done=None, on_postpone=None, on_focus=None,
                  on_close=None) -> None:
    ensure_styles()

    from backend.core.reviews.recommendation_service import get_next_action
    na = get_next_action(task)

    with ui.element("div").classes("cp"):
        # En-tête
        with ui.element("div").classes("cp-head"):
            ui.label(_ring_glyph(task.mastery_score)).classes("cp-head-ring")
            ui.label(task.course_title).classes("cp-head-title")
            ui.label(task.item_number or "").classes("cp-head-id")
            _x = ui.label("✕").classes("cp-close")
            if on_close is not None:
                _x.on("click", lambda: on_close())

        # Pourquoi maintenant
        with ui.element("div").classes("cp-section"):
            ui.label("Pourquoi maintenant").classes("cp-label")
            with ui.element("div").classes("cp-why"):
                ui.label(na.reason or na.label)

        # Maîtrise
        with ui.element("div").classes("cp-section"):
            ui.label("Maîtrise").classes("cp-label")
            mastery_indicator(task.mastery_score, task.mastery_level)

        # Note Obsidian (stub — session 4)
        with ui.element("div").classes("cp-section"):
            ui.label("Note Obsidian").classes("cp-label")
            ui.label("— (détail item, à venir)").classes("cp-stub")

        # Notions reliées (stub — session 4)
        with ui.element("div").classes("cp-section"):
            ui.label("Notions reliées").classes("cp-label")
            ui.label("— (détail item, à venir)").classes("cp-stub")

        # Ressources
        with ui.element("div").classes("cp-section"):
            ui.label("Ressources").classes("cp-label")
            if task.has_pdf:
                ui.link("↗ PDF officiel", f"/pdf/{task.course_id}", new_tab=True).classes("cp-res")
            if task.agregation_fiche_edn:
                ui.link("↗ Fiche EDN / Obsidian", task.agregation_fiche_edn, new_tab=True).classes("cp-res")
            if not task.has_pdf and not task.agregation_fiche_edn:
                ui.label("— aucune ressource liée").classes("cp-stub")

        # Pied
        with ui.element("div").classes("cp-foot"):
            _term = ui.element("div").classes("cp-btn primary")
            with _term:
                ui.label("Terminer")
            if on_done is not None:
                _term.on("click", lambda t=task: on_done(t))

            _post = ui.element("div").classes("cp-btn")
            with _post:
                ui.label("Reporter")
            if on_postpone is not None:
                _post.on("click", lambda t=task: on_postpone(t))

            _foc = ui.element("div").classes("cp-btn")
            with _foc:
                ui.label("Focus")
            if on_focus is not None:
                _foc.on("click", lambda t=task: on_focus(t))
