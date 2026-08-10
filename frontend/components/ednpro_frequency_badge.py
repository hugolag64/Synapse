"""Compact EDNpro priority badge shared by item-oriented views."""

from __future__ import annotations

from nicegui import ui

_PRIORITY_PRESENTATION = {
    "indispensable": ("INDISPENSABLE", "var(--danger)"),
    "important": ("IMPORTANT", "var(--warning)"),
    "basique": ("BASIQUE", "var(--accent)"),
    "jamais_tombe": ("JAMAIS TOMBÉ", "var(--text-dim)"),
}

_CSS = """
.edn-frequency-badge { display:inline-flex; align-items:center; gap:5px; min-width:0;
  padding:3px 7px; border:1px solid color-mix(in srgb, var(--edn-frequency-color) 32%, var(--border));
  border-radius:999px; background:color-mix(in srgb, var(--edn-frequency-color) 10%, var(--bg));
  color:var(--edn-frequency-color); font-family:var(--font-mono); font-size:9px;
  font-weight:700; letter-spacing:.045em; line-height:1.25; white-space:nowrap; }
.edn-frequency-badge.compact { gap:4px; padding:2px 6px; font-size:8.5px; }
.edn-frequency-dot { width:6px; height:6px; flex:0 0 6px; border-radius:50%;
  background:var(--edn-frequency-color); }
.edn-frequency-badge.compact .edn-frequency-dot { width:5px; height:5px; flex-basis:5px; }
"""
_injected = {"done": False}


def _priority_key(frequency: dict | None) -> str:
    priority = str((frequency or {}).get("priority") or "jamais_tombe").strip().lower()
    return priority if priority in _PRIORITY_PRESENTATION else "jamais_tombe"


def frequency_badge_text(frequency: dict | None) -> str:
    """Return the user-facing EDNpro priority label."""
    return _PRIORITY_PRESENTATION[_priority_key(frequency)][0]


def frequency_badge_tooltip(frequency: dict | None) -> str:
    """Return the detailed frequency text shown when hovering the badge."""
    if not frequency:
        return "Fréquence EDNpro indisponible"
    sessions = max(0, int(frequency.get("session_count") or 0))
    questions = max(0, int(frequency.get("question_count") or 0))
    session_label = "session" if sessions == 1 else "sessions"
    question_label = "question" if questions == 1 else "questions"
    years = ", ".join(str(year) for year in (frequency.get("years") or []))
    return (
        f"{sessions} {session_label} · {questions} {question_label} · "
        f"{years or 'années indisponibles'}"
    )


def ensure_styles() -> None:
    if not _injected["done"]:
        ui.add_head_html(f"<style>{_CSS}</style>", shared=True)
        _injected["done"] = True


def ednpro_frequency_badge(frequency: dict | None, *, compact: bool = False) -> None:
    """Render an accessible, compact EDNpro priority badge."""
    ensure_styles()
    key = _priority_key(frequency)
    label = frequency_badge_text(frequency)
    details = frequency_badge_tooltip(frequency)
    classes = "edn-frequency-badge compact" if compact else "edn-frequency-badge"
    with ui.element("span").classes(classes).style(
        f"--edn-frequency-color:{_PRIORITY_PRESENTATION[key][1]}"
    ).props(f'role="status" aria-label="{label} — {details}"').tooltip(details):
        ui.element("span").classes("edn-frequency-dot")
        ui.label(label)
