"""review_timeline — timeline J3/J7/J14/J30 du détail item (refonte, session 4).

Composant purement présentationnel : l'appelant fournit les étapes déjà résolues
(`build_stages`), le composant ne fait que peindre. Grammaire de statut : le point
porte l'urgence (rouge en retard · ambre aujourd'hui · vert fait · gris futur ou
non planifié), l'état passé/futur passe par l'opacité, jamais par un badge coloré.
"""
from __future__ import annotations

import datetime

from nicegui import ui

_CSS = """
.rt { display:flex; flex-direction:column; }
.rt-row { display:flex; align-items:center; gap:12px; height:38px; padding:0 10px; border-radius:6px;
  transition: background var(--duration-fast) var(--ease-standard); }
.rt-row:hover { background:var(--surface); }
.rt-row.past { opacity:.55; }
.rt-dot { width:7px; height:7px; border-radius:50%; flex:0 0 7px; }
.rt-cycle { font-family:var(--font-mono); font-size:11.5px; color:var(--text-muted); flex:0 0 56px; }
.rt-date { font-size:12.5px; color:var(--text); flex:1 1 auto; }
.rt-state { font-size:11.5px; color:var(--text-dim); flex:0 0 auto; }
.rt-action { font-size:12px; font-weight:500; color:var(--accent-text); background:var(--accent);
  border-radius:6px; padding:4px 10px; cursor:pointer; flex:0 0 auto;
  transition: background var(--duration-fast) var(--ease-standard); }
.rt-action:hover { background:var(--accent-hover); }
.rt-empty { font-size:12.5px; color:var(--text-dim); padding:14px 10px; }
"""
_injected = {"done": False}

_CYCLES = [
    ("1re lecture", "date_1ere_lecture"),
    ("J3", "lecture_j3_college"),
    ("J7", "lecture_j7_college"),
    ("J14", "lecture_j14_college"),
    ("J30", "lecture_j30_college"),
]

_STATE_COLOR = {
    "done":   "var(--success)",
    "late":   "var(--danger)",
    "today":  "var(--warning)",
    "future": "var(--text-dim)",
    "none":   "var(--text-dim)",
}
_STATE_LABEL = {
    "done":   "fait",
    "late":   "en retard",
    "today":  "aujourd'hui",
    "future": "à venir",
    "none":   "non planifié",
}

_MONTHS_FR = ["jan", "fév", "mar", "avr", "mai", "juin",
              "juil", "août", "sep", "oct", "nov", "déc"]


def ensure_styles() -> None:
    """Injecte le CSS du composant (à appeler au build synchrone de la page)."""
    if not _injected["done"]:
        ui.add_head_html(f"<style>{_CSS}</style>", shared=True)
        _injected["done"] = True


def _row_get(row, key, default=None):
    """Accès tolérant : local_store renvoie des sqlite3.Row, pas des dict."""
    try:
        val = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if val is None else val


def _as_date(value):
    if value is None:
        return None
    if hasattr(value, "timetuple") and not isinstance(value, str):
        return value if isinstance(value, datetime.date) else None
    if isinstance(value, str) and len(value) >= 10:
        try:
            return datetime.date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _fmt(d: datetime.date | None) -> str:
    """Jour + mois, avec l'année dès qu'elle diffère de l'année courante —
    sans quoi un cycle bouclé en oct. 2025 s'affiche « 2 oct » et se lit comme
    une échéance à venir."""
    if not d:
        return "—"
    base = f"{d.day} {_MONTHS_FR[d.month - 1]}"
    return base if d.year == datetime.date.today().year else f"{base} {d.year}"


def build_stages(course, review_hist: list | None = None) -> list[dict]:
    """Résout les 5 étapes du cycle depuis les dates Notion + l'historique local.

    Une étape est « done » si l'historique local la marque validée, ou si sa date
    planifiée est passée (le backend n'avance la date qu'après lecture).
    """
    today = datetime.date.today()
    done_cycles = {
        str(_row_get(row, "review_type", "")).upper()
        for row in (review_hist or [])
        if _row_get(row, "status") == "done"
    }

    stages: list[dict] = []
    for label, attr in _CYCLES:
        d = _as_date(getattr(course, attr, None))
        if label.upper() in done_cycles:
            state = "done"
        elif d is None:
            state = "none"
        elif d < today:
            state = "done" if label == "1re lecture" else "late"
        elif d == today:
            state = "today"
        else:
            state = "future"
        stages.append({"cycle": label, "date": d, "state": state})
    return stages


def review_timeline(stages: list[dict], *, on_review=None) -> None:
    """Peint la timeline. `on_review` reçoit le dict d'étape due (late/today)."""
    ensure_styles()

    if not stages:
        with ui.element("div").classes("rt"):
            ui.label("Aucun cycle de révision planifié.").classes("rt-empty")
        return

    with ui.element("div").classes("rt"):
        for st in stages:
            state = st["state"]
            cls = "rt-row" + (" past" if state in ("done", "none") else "")
            with ui.element("div").classes(cls):
                ui.element("span").classes("rt-dot").style(
                    f"background:{_STATE_COLOR.get(state, 'var(--text-dim)')}"
                )
                ui.label(st["cycle"]).classes("rt-cycle")
                ui.label(_fmt(st["date"])).classes("rt-date")
                ui.label(_STATE_LABEL.get(state, "")).classes("rt-state")
                if state in ("late", "today") and on_review is not None:
                    btn = ui.element("div").classes("rt-action")
                    with btn:
                        ui.label("Réviser")
                    btn.on("click", lambda s=st: on_review(s))
