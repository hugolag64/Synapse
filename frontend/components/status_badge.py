"""Shared labels and CSS classes for pedagogical statuses."""

from __future__ import annotations

import unicodedata

STATUS_LABELS = {
    "a_lire": "À lire",
    "lu_sans_preuve": "Lu · maîtrise non évaluée",
    "à préparer": "À préparer",
    "à lire": "À lire",
    "non_commence": "Non commencé",
    "en construction": "En construction",
    "à consolider": "À consolider",
    "à entraîner": "À entraîner",
    "solide": "Solide",
    "correct": "Correct",
    "fragile": "Fragile",
    "critique": "Critique",
    "maîtrisé": "Maîtrisé",
}

STATUS_ORDER = (
    "a_lire",
    "lu_sans_preuve",
    "à préparer",
    "en construction",
    "à consolider",
    "à entraîner",
    "fragile",
    "critique",
    "maîtrisé",
    "correct",
    "solide",
    "non_commence",
)

STATUS_COLORS = {
    "a_lire": "var(--text-dim)",
    "lu_sans_preuve": "var(--warning)",
    "à préparer": "var(--text-dim)",
    "en construction": "var(--info)",
    "à consolider": "var(--info)",
    "à entraîner": "var(--accent)",
    "fragile": "var(--warning)",
    "critique": "var(--danger)",
    "maîtrisé": "var(--success)",
    "correct": "var(--text-muted)",
    "solide": "var(--success)",
    "non_commence": "var(--text-dim)",
}


def status_label(status: str | None) -> str:
    return STATUS_LABELS.get(str(status or "").strip().lower(), "—")


def status_class(status: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(status or "").strip().lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return text.replace("_", "-").replace(" ", "-")
