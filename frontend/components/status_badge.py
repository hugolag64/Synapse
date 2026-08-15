"""Shared labels and CSS classes for pedagogical statuses."""

from __future__ import annotations


STATUS_LABELS = {
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


def status_label(status: str | None) -> str:
    return STATUS_LABELS.get(str(status or "").strip().lower(), "—")


def status_class(status: str | None) -> str:
    return (
        str(status or "").strip().lower()
        .replace("_", "-")
        .replace(" ", "-")
        .replace("à", "a")
        .replace("î", "i")
    )
