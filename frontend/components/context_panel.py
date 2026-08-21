"""context_panel — panneau contextuel droit de la vue Aujourd'hui (refonte).

En-tête (forme + titre court + id cliquable → détail item + ✕) puis sections :
  • Pourquoi maintenant (encadré accent-wash) — raison via get_next_action.
  • Maîtrise (barre + score).
  • Note Obsidian — extrait réel de la note du vault (session 4).
  • Notions reliées — voisins du graphe sémantique (session 4).
  • Ressources (PDF / Obsidian).
Pied : Terminer (primaire) / Reporter / Focus.
"""
from __future__ import annotations

from nicegui import ui
from loguru import logger

from frontend.components.mastery_indicator import mastery_indicator
from frontend.components.relation_graph import neighbors_of
from frontend.components.study_task_row import _ring_glyph
from backend.state.store import data_store
from backend.core.reviews.consolidation import (
    is_algorithmic_postpone, postpone_days_for_task,
)
from frontend.components.course_quick_actions import open_pdf_wizard

NOTE_EXCERPT_CHARS = 220
MAX_RELATED = 4
POSTPONE_CHOICES: tuple[tuple[int, str], ...] = (
    (1, "+1 jour"),
    (3, "+3 jours"),
    (7, "+1 semaine"),
)

_CSS = """
.cp { display:flex; flex-direction:column; gap:0; height:100%; }
.cp-head { display:flex; align-items:center; gap:8px; padding:0 4px 12px; border-bottom:1px solid var(--border); }
.cp-head-ring { font-size:14px; color:var(--text-muted); flex:0 0 auto; }
.cp-head-title { font-size:14px; font-weight:600; color:var(--text); flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.cp-head-id { font-family:var(--font-mono); font-size:11px; color:var(--text-dim) !important; flex:0 0 auto;
  text-decoration:none !important; }
.cp-head-id:hover { color:var(--accent) !important; text-decoration:underline !important; }
.cp-close { color:var(--text-dim); cursor:pointer; font-size:13px; flex:0 0 auto; line-height:1; }
.cp-section { padding:14px 4px 0; }
.cp-label { font-size:10px; text-transform:uppercase; letter-spacing:.04em; color:var(--text-dim); font-weight:600; margin-bottom:6px; }
.cp-why { background:var(--accent-wash); border-radius:6px; padding:10px 12px; font-size:12.5px; line-height:1.5; color:var(--text); }
.cp-stub { font-size:12px; color:var(--text-dim); font-style:normal; padding:2px 0; }
.cp-note { background:var(--surface); border-radius:6px; padding:9px 11px; font-size:12px;
  line-height:1.55; color:var(--text-muted); max-height:104px; overflow:hidden; }
.cp-rel { display:flex; align-items:baseline; gap:6px; font-size:12.5px; color:var(--accent) !important;
  text-decoration:none !important; padding:3px 0; }
.cp-rel:hover { text-decoration:underline !important; }
.cp-rel .lbl { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.cp-rel .n { font-family:var(--font-mono); font-size:10.5px; color:var(--text-dim);
  margin-left:auto; flex:0 0 auto; }
.cp-res { display:flex; align-items:center; gap:6px; font-size:12.5px; color:var(--accent); cursor:pointer; padding:3px 0; text-decoration:none; }
.cp-res:hover { text-decoration:underline; }
.cp-foot { margin-top:auto; padding-top:14px; display:flex; gap:8px; }
.cp-btn { position:relative; flex:1; height:32px; border-radius:6px; font-size:12.5px; font-weight:500; cursor:pointer;
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


def _note_excerpt(course_id: str) -> str | None:
    """Premières lignes de la note Obsidian du cours (frontmatter retiré)."""
    from backend.state.store import data_store
    from backend.config.settings import settings
    from backend.core.obsidian.service import obsidian_service

    if not settings.obsidian_vault_path:
        return None
    course = next((c for c in data_store.cours if c.id == course_id), None)
    if course is None:
        return None
    try:
        path = obsidian_service.find_course_note(course)
        if path is None or not path.exists():
            return None
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning(f"note Obsidian illisible pour {course_id}: {exc}")
        return None

    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) == 3:
            raw = parts[2]

    # Aplatir en texte lisible : les marqueurs markdown collés bout à bout
    # (« ## 1. À savoir - - — ### ») sont illisibles dans un extrait de 220 car.
    kept: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or set(line) <= {"-", "—", "–", "*", "_", "="}:
            continue          # séparateurs et lignes vides
        kept.append(line.lstrip("#>*-+ ").strip())
    body = " · ".join(k for k in kept if k)
    if not body:
        return None
    return body[:NOTE_EXCERPT_CHARS] + ("…" if len(body) > NOTE_EXCERPT_CHARS else "")


def _related_courses(course_id: str) -> list:
    """Cours voisins dans le graphe sémantique, résolus depuis le store."""
    from backend.state.store import data_store

    by_id = {c.id: c for c in data_store.cours}
    return [by_id[cid] for cid in neighbors_of(course_id, limit=MAX_RELATED)
            if cid in by_id]


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
            ui.link(task.item_number or "—", f"/cours/{task.course_id}").classes(
                "cp-head-id"
            ).tooltip("Ouvrir le détail de l'item")
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

        # Note Obsidian — extrait réel
        with ui.element("div").classes("cp-section"):
            ui.label("Note Obsidian").classes("cp-label")
            excerpt = _note_excerpt(task.course_id)
            if excerpt:
                ui.label(excerpt).classes("cp-note")
            else:
                ui.label("— aucune note dans le vault").classes("cp-stub")

        # Notions reliées — voisins du graphe sémantique
        with ui.element("div").classes("cp-section"):
            ui.label("Notions reliées").classes("cp-label")
            related = _related_courses(task.course_id)
            if not related:
                ui.label("— aucune").classes("cp-stub")
            for c in related:
                link = ui.link(target=f"/cours/{c.id}").classes("cp-rel")
                with link:
                    ui.label(f"◇ {c.title}").classes("lbl")
                    ui.label(str(c.display_item_number or c.item_number or "")).classes("n")

        # Ressources
        with ui.element("div").classes("cp-section"):
            ui.label("Ressources").classes("cp-label")
            if task.has_pdf:
                ui.link("↗ PDF officiel", f"/pdf/{task.course_id}", new_tab=True).classes("cp-res")
            course = next((c for c in data_store.cours if c.id == task.course_id), None)
            if course is not None:
                _edit_pdf = ui.element("div").classes("cp-res")
                with _edit_pdf:
                    ui.label("↻ Modifier le PDF")
                _edit_pdf.on(
                    "click",
                    lambda c=course: open_pdf_wizard(
                        c, task.context, lambda: ui.navigate.reload(), ui.context.client
                    ),
                )
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

            # « Reporter » doit décaler l'échéance, pas ouvrir le focus. Le
            # cycle de lecture J1→J30 se décale à la main ; un item à consolider
            # est replanifié par l'algorithme, selon sa maîtrise.
            _algorithmic = is_algorithmic_postpone(task)
            _post = ui.element("div").classes("cp-btn")
            with _post:
                ui.label("Reporter")
                if on_postpone is not None and not _algorithmic:
                    with ui.menu() as _post_menu:
                        for _days, _lbl in POSTPONE_CHOICES:
                            ui.menu_item(
                                _lbl,
                                on_click=lambda t=task, d=_days: on_postpone(t, d),
                            ).classes("text-xs")
            if on_postpone is not None:
                if _algorithmic:
                    _post.on("click", lambda t=task: on_postpone(t, None))
                    _post.tooltip(
                        f"Replanifié dans {postpone_days_for_task(task)} j "
                        f"— maîtrise {task.mastery_level or 'inconnue'}"
                    )
                else:
                    _post.on("click", _post_menu.open)

            _foc = ui.element("div").classes("cp-btn")
            with _foc:
                ui.label("Focus")
            if on_focus is not None:
                _foc.on("click", lambda t=task: on_focus(t))
