"""relation_graph — mini-graphe « Notions reliées » du détail item (session 4).

Nœud central = l'item courant (accent) ; jusqu'à 4 voisins issus du graphe
sémantique existant (`data_store.semantic_graph`, construit par
`backend.core.graph.builder`), disposés en éventail. Les voisins sont **colorés
par urgence** (grammaire de statut : rouge en retard · ambre échéance du jour ·
gris sinon), jamais par type d'arête. Une phrase suggère le voisin le plus faible.

Aucun accès backend nouveau : on lit le graphe déjà en mémoire + les scores de
maîtrise fournis par l'appelant.
"""
from __future__ import annotations

import math

from nicegui import ui
from loguru import logger

MAX_NEIGHBORS = 4

_CSS = """
.rg-wrap { display:flex; flex-direction:column; gap:8px; }
.rg-svg { width:100%; height:auto; display:block; overflow:visible; }
.rg-caption { font-size:12px; color:var(--text-muted); line-height:1.5; }
.rg-caption b { font-weight:600; color:var(--text); }
.rg-empty { font-size:12px; color:var(--text-dim); padding:12px 0; }
"""
_injected = {"done": False}


def ensure_styles() -> None:
    """Injecte le CSS du composant (à appeler au build synchrone de la page)."""
    if not _injected["done"]:
        ui.add_head_html(f"<style>{_CSS}</style>", shared=True)
        _injected["done"] = True


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _short(title: str, limit: int = 16) -> str:
    t = (title or "").strip()
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "…"


def _graph() -> dict:
    """Graphe sémantique, rechargé depuis SQLite s'il est vide en mémoire.

    `data_store.rebuild_semantic_graph()` n'est appelé qu'après une sync Notion :
    au démarrage sur cache (<12 h) le graphe en mémoire reste vide alors que la
    table `course_edges` est peuplée. `load_graph_from_db()` existe mais n'était
    appelée nulle part — on s'en sert ici, en mémoïsant sur le store.
    """
    from backend.state.store import data_store

    if data_store.semantic_graph:
        return data_store.semantic_graph
    try:
        from backend.core.reviews.local_store import load_graph_from_db
        data_store.semantic_graph = load_graph_from_db()
    except Exception as exc:
        logger.warning(f"graphe sémantique indisponible : {exc}")
        return {}
    return data_store.semantic_graph or {}


def neighbors_of(course_id: str, *, limit: int = MAX_NEIGHBORS) -> list:
    """Voisins les plus liés (arêtes de poids décroissant, cibles dédupliquées)."""
    edges = _graph().get(course_id) or []
    best: dict[str, float] = {}
    for e in edges:
        tgt = getattr(e, "target_id", None)
        if not tgt or tgt == course_id:
            continue
        w = float(getattr(e, "weight", 0) or 0)
        if w > best.get(tgt, -1.0):
            best[tgt] = w
    ordered = sorted(best.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [tgt for tgt, _ in ordered]


def relation_graph(center_label: str, neighbors: list[dict]) -> None:
    """Graphe + suggestion.

    center_label : id court affiché au centre (ex. « 221 »).
    neighbors    : [{'label', 'score', 'urgency'}] — urgency ∈ late|today|none.
                   `score` peut être None (maîtrise inconnue).
    """
    ensure_styles()

    if not neighbors:
        with ui.element("div").classes("rg-wrap"):
            ui.label("Aucune notion reliée pour l'instant.").classes("rg-empty")
        return

    urgency_color = {
        "late": "var(--danger)",
        "today": "var(--warning)",
        "none": "var(--text-dim)",
    }

    # Géométrie : l'éventail doit tenir dans le viewBox. Avec r=78 et ±52° les
    # nœuds extrêmes sortaient du cadre (dy = ±61 pour une demi-hauteur de 48).
    w, h = 280.0, 120.0
    cx, cy = 58.0, h / 2
    n = len(neighbors)
    spread = math.radians(50)
    radius = 64.0

    nodes = []
    for i, nb in enumerate(neighbors):
        frac = 0.5 if n == 1 else i / (n - 1)
        angle = -spread + 2 * spread * frac
        nodes.append((
            cx + radius * math.cos(angle),
            cy + radius * math.sin(angle),
            nb,
        ))

    parts = []
    for x, y, nb in nodes:
        parts.append(
            f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{x:.1f}" y2="{y:.1f}" '
            f'stroke="var(--border)" stroke-width="1"/>'
        )
    parts.append(
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="15" fill="var(--accent)"/>'
        f'<text x="{cx:.1f}" y="{cy + 3.5:.1f}" text-anchor="middle" '
        f'font-family="var(--font-mono)" font-size="10" fill="var(--accent-text)">'
        f'{_esc(center_label)}</text>'
    )
    for x, y, nb in nodes:
        color = urgency_color.get(nb.get("urgency", "none"), urgency_color["none"])
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}"/>'
            f'<text x="{x + 7:.1f}" y="{y + 3.5:.1f}" font-family="var(--font-sans)" '
            f'font-size="9.5" fill="var(--text-muted)">{_esc(_short(nb.get("label", "")))}</text>'
        )

    svg = (f'<svg class="rg-svg" viewBox="0 0 {w:.0f} {h:.0f}" role="img" '
           f'aria-label="Graphe des notions reliées à l\'item {_esc(center_label)}">'
           + "".join(parts) + "</svg>")

    with ui.element("div").classes("rg-wrap"):
        ui.html(svg)
        scored = [nb for nb in neighbors if nb.get("score") is not None]
        with ui.element("div").classes("rg-caption"):
            if scored:
                weakest = min(scored, key=lambda nb: nb["score"])
                ui.html(
                    f'{len(neighbors)} liens · le plus faible : '
                    f'<b>{_esc(weakest["label"])}</b> ({int(weakest["score"])}) — '
                    f'à revoir en même temps.'
                )
            else:
                ui.html(f"{len(neighbors)} liens · maîtrise des voisins inconnue.")
