"""mastery_indicator — barre de maîtrise + score (refonte cockpit).

Grammaire de statut : la maîtrise passe par une barre + un score 0–100 dont la
couleur encode la santé (solide vert ≥80 · correct gris 55–79 · fragile ambre
30–54 · critique rouge <30). Réutilisable (Aujourd'hui, Détail item…).
"""
from nicegui import ui

_LEVEL_COLOR = {
    "solide":   "var(--success)",
    "correct":  "var(--text-muted)",
    "fragile":  "var(--warning)",
    "critique": "var(--danger)",
}

_CSS = """
.mastery-ind { display:flex; align-items:center; gap:8px; }
.mastery-track { flex:1; height:5px; border-radius:3px; background:var(--surface-hover); overflow:hidden; }
.mastery-fill { height:100%; border-radius:3px; transition: width var(--duration-base) var(--ease-standard); }
.mastery-score { font-family:var(--font-mono); font-size:12px; font-weight:600; min-width:20px; text-align:right; }
"""
_injected = {"done": False}


def _level_from_score(score) -> str:
    if score is None:
        return "correct"
    if score >= 80:
        return "solide"
    if score >= 55:
        return "correct"
    if score >= 30:
        return "fragile"
    return "critique"


def ensure_styles() -> None:
    """Injecte le CSS du composant (à appeler au build synchrone de la page)."""
    if not _injected["done"]:
        ui.add_head_html(f"<style>{_CSS}</style>", shared=True)
        _injected["done"] = True


def mastery_indicator(score, level: str | None = None, *, width: str = "100%",
                      show_score: bool = True) -> None:
    """Barre + score. `score` peut être None (affiche « — », couleur neutre)."""
    ensure_styles()

    lvl = level or _level_from_score(score)
    color = _LEVEL_COLOR.get(lvl, "var(--text-muted)")
    pct = max(0, min(100, score if score is not None else 0))

    with ui.element("div").classes("mastery-ind").style(f"width:{width}"):
        with ui.element("div").classes("mastery-track"):
            ui.element("div").classes("mastery-fill").style(
                f"width:{pct}%; background:{color}"
            )
        if show_score:
            ui.label(str(score) if score is not None else "—").classes(
                "mastery-score"
            ).style(f"color:{color}")


def dual_rank_badges(score_rang_a: int | None, score_rang_b: int | None) -> None:
    """Affiche côte à côte les badges explicites Rang A % et Rang B %."""
    ensure_styles()
    val_a = f"{score_rang_a}%" if score_rang_a is not None else "—"
    val_b = f"{score_rang_b}%" if score_rang_b is not None else "—"
    
    color_a = "#059669" if (score_rang_a or 0) >= 75 else "#DC2626"
    bg_a = "rgba(5, 150, 105, 0.12)" if (score_rang_a or 0) >= 75 else "rgba(220, 38, 38, 0.12)"
    icon_a = "shield" if (score_rang_a or 0) >= 75 else "warning"

    with ui.element("div").classes("flex items-center gap-1.5 text-xs font-mono"):
        with ui.element("span").classes("px-1.5 py-0.5 rounded flex items-center gap-1 font-semibold").style(
            f"background:{bg_a}; color:{color_a}; border: 1px solid {color_a}40;"
        ):
            ui.icon(icon_a, size="12px")
            ui.label(f"A: {val_a}")

        with ui.element("span").classes("px-1.5 py-0.5 rounded flex items-center gap-1 font-semibold").style(
            "background:rgba(99, 102, 241, 0.12); color:#4F46E5; border: 1px solid rgba(99, 102, 241, 0.3);"
        ):
            ui.icon("military_tech", size="12px")
            ui.label(f"B: {val_b}")

