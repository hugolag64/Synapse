"""forgetting_curve — courbe d'oubli SVG du détail item (refonte, session 4).

Projette le score de maîtrise dans les 30 prochains jours *sans révision*, avec
un repère sur l'échéance à venir (« J+7 · 42 ») et le point de départ (« auj. 48 »).

La projection réutilise le modèle adaptatif partagé quand une stabilité de
rétention est disponible ; sinon elle garde le fallback historique piloté par le
cycle de révision courant.
"""
from __future__ import annotations

import math

from nicegui import ui

from backend.core.knowledge.retention import MASTERY_FLOOR, project_retention

# ── Paramètres du modèle (présentation) ───────────────────────────────────────
HALF_LIFE_FACTOR = 2.0      # demi-vie = facteur × intervalle du cycle courant
DEFAULT_INTERVAL_D = 7      # cycle inconnu → on suppose J7
SCORE_FLOOR = 20            # asymptote : on n'oublie jamais tout
HORIZON_D = 30              # largeur de la projection

_CYCLE_INTERVAL = {"J3": 3, "J7": 7, "J14": 14, "J30": 30, "consolidation": 21}

_CSS = """
.fc-wrap { display:flex; flex-direction:column; gap:8px; }
.fc-svg { width:100%; height:auto; display:block; overflow:visible; }
.fc-caption { font-size:12px; color:var(--text-muted); line-height:1.5; }
.fc-caption b { font-weight:600; color:var(--text); }
.fc-empty { font-size:12px; color:var(--text-dim); padding:12px 0; }
"""
_injected = {"done": False}


def ensure_styles() -> None:
    """Injecte le CSS du composant (à appeler au build synchrone de la page)."""
    if not _injected["done"]:
        ui.add_head_html(f"<style>{_CSS}</style>", shared=True)
        _injected["done"] = True


def cycle_interval(review_type: str | None) -> int:
    return _CYCLE_INTERVAL.get(review_type or "", DEFAULT_INTERVAL_D)


def project_score(
    score0: int,
    days: float,
    interval_d: int,
    stability_days: float | None = None,
) -> float:
    """Score projeté après `days` jours sans révision (décroissance vers le plancher)."""
    if stability_days is not None and stability_days > 0:
        return project_retention(score0, stability_days, days)

    score = max(float(MASTERY_FLOOR), min(100.0, float(score0)))
    if days <= 0:
        return score
    half_life = max(1.0, HALF_LIFE_FACTOR * interval_d)
    decayed = (score - MASTERY_FLOOR) * math.exp(-days * math.log(2) / half_life)
    projected = MASTERY_FLOOR + decayed
    return max(float(MASTERY_FLOOR), min(100.0, projected))


def _health(score: float) -> str:
    if score >= 80:
        return "solide"
    if score >= 55:
        return "correct"
    if score >= 30:
        return "fragile"
    return "critique"


def forgetting_curve(score0, review_type: str | None = None,
                     horizon_days: int = HORIZON_D,
                     marker_days: int | None = None,
                     *, stability_days: float | None = None) -> None:
    """Courbe d'oubli + phrase de synthèse.

    score0       : maîtrise actuelle (None → composant vide, pas de fausse courbe).
    review_type  : cycle courant (J3/J7/…) — pilote la vitesse d'oubli.
    marker_days  : jours jusqu'à la prochaine échéance (repère rouge pointillé).
    """
    ensure_styles()

    if score0 is None:
        with ui.element("div").classes("fc-wrap"):
            ui.label("Pas encore assez de données pour projeter la maîtrise.").classes("fc-empty")
        return

    interval = cycle_interval(review_type)
    mark_d = marker_days if marker_days is not None else interval
    mark_d = max(1, min(horizon_days, mark_d))

    # Géométrie (viewBox fixe, largeur fluide)
    w, h = 280.0, 96.0
    pad_l, pad_r, pad_t, pad_b = 6.0, 34.0, 10.0, 16.0
    plot_w, plot_h = w - pad_l - pad_r, h - pad_t - pad_b

    def _x(day: float) -> float:
        return pad_l + plot_w * (day / horizon_days)

    def _y(score: float) -> float:
        return pad_t + plot_h * (1 - max(0.0, min(100.0, score)) / 100.0)

    pts = [(_x(d), _y(project_score(score0, d, interval, stability_days=stability_days)))
           for d in range(0, horizon_days + 1)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{pts[0][0]:.1f},{pad_t + plot_h:.1f} {line} {pts[-1][0]:.1f},{pad_t + plot_h:.1f}"

    mark_score = project_score(score0, mark_d, interval, stability_days=stability_days)
    mx, my = _x(mark_d), _y(mark_score)

    svg = f"""
<svg class="fc-svg" viewBox="0 0 {w:.0f} {h:.0f}" role="img"
     aria-label="Projection adaptative actuelle sans révision : {int(round(score0))} aujourd'hui,
     {int(round(mark_score))} dans {mark_d} jours">
  <line x1="{pad_l}" y1="{pad_t + plot_h:.1f}" x2="{w - pad_r:.1f}" y2="{pad_t + plot_h:.1f}"
        stroke="var(--border)" stroke-width="1"/>
  <polygon points="{area}" fill="var(--accent)" opacity="0.08"/>
  <polyline points="{line}" fill="none" stroke="var(--accent)" stroke-width="1.5"
            stroke-linejoin="round" stroke-linecap="round"/>
  <line x1="{mx:.1f}" y1="{pad_t:.1f}" x2="{mx:.1f}" y2="{pad_t + plot_h:.1f}"
        stroke="var(--danger)" stroke-width="1" stroke-dasharray="3 3" opacity="0.7"/>
  <circle cx="{mx:.1f}" cy="{my:.1f}" r="3" fill="var(--danger)"/>
  <text x="{mx + 5:.1f}" y="{my - 5:.1f}" font-family="var(--font-mono)" font-size="9.5"
        fill="var(--danger)">J+{mark_d} · {int(round(mark_score))}</text>
  <circle cx="{pts[0][0]:.1f}" cy="{pts[0][1]:.1f}" r="3" fill="var(--accent)"/>
  <text x="{pts[0][0] + 5:.1f}" y="{pts[0][1] - 6:.1f}" font-family="var(--font-mono)"
        font-size="9.5" fill="var(--text-muted)">auj. {int(round(score0))}</text>
</svg>
"""

    with ui.element("div").classes("fc-wrap"):
        ui.html(svg)
        drop = int(round(score0)) - int(round(mark_score))
        with ui.element("div").classes("fc-caption"):
            if drop <= 0:
                ui.html(
                    f"Projection adaptative actuelle sans révision : stable sur {mark_d} j — "
                    f"<b>{int(round(mark_score))}</b> ({_health(mark_score)})."
                )
            else:
                ui.html(
                    f"Projection adaptative actuelle sans révision → "
                    f"<b>{int(round(mark_score))}</b> dans {mark_d} j "
                    f"({_health(mark_score)}), soit −{drop}."
                )
