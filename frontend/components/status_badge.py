"""Shared labels and CSS classes for pedagogical statuses."""

from __future__ import annotations

import unicodedata

STATUS_LABELS = {
    "à préparer": "À préparer",
    "à lire": "À lire",
    "non évalué": "Non évalué",
    "en construction": "En construction",
    "à consolider": "À consolider",
    "fragile": "Fragile",
    "critique": "Critique",
    "maîtrisé": "Maîtrisé",
    "non_commence": "Non commencé",
}

# Échelle unique : celle produite par `get_item_mastery` (mastery.py). Les clés
# `a_lire`/`lu_sans_preuve`/`correct`/`solide`/`à entraîner` ont été retirées
# car aucun code ne les produit plus — elles dédoublaient ce vocabulaire (N11,
# Q4). `non_commence` reste : encore émis par le repli legacy de
# `_pilotage_summary` (N05, à traiter séparément).
STATUS_ORDER = (
    "à préparer",
    "à lire",
    "non évalué",
    "en construction",
    "à consolider",
    "fragile",
    "critique",
    "maîtrisé",
    "non_commence",
)

STATUS_COLORS = {
    "à préparer": "var(--text-dim)",
    "à lire": "var(--text-dim)",
    "non évalué": "var(--info)",
    "en construction": "var(--info)",
    "à consolider": "var(--info)",
    "fragile": "var(--warning)",
    "critique": "var(--danger)",
    "maîtrisé": "var(--success)",
    "non_commence": "var(--text-dim)",
}


def status_label(status: str | None) -> str:
    return STATUS_LABELS.get(str(status or "").strip().lower(), "—")


def status_class(status: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(status or "").strip().lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return text.replace("_", "-").replace(" ", "-")
