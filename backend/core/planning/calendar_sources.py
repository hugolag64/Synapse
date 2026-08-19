"""Gestion des IDs de calendrier Google supplémentaires (préférence planning)."""

from __future__ import annotations


FAC_CALENDAR_ID = "kvj2875m68cng7oeiq6mbfh8k20ha1ru@import.calendar.google.com"
FAC_CALENDAR_LABEL = "FAC"


def list_calendar_sources(preferences: dict) -> list[dict]:
    """Lit planning_calendar_sources depuis les préférences, normalisé.

    Retourne une liste vide si la clé est absente ou mal formée (jamais
    d'exception — même défense que les autres lectures de préférences
    planning, ex. _target_for dans planning_cockpit.py).
    """
    raw = preferences.get("planning_calendar_sources") if isinstance(preferences, dict) else None
    if not isinstance(raw, list):
        return []
    result: list[dict] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        calendar_id = str(entry.get("id", "")).strip()
        if not calendar_id:
            continue
        label = str(entry.get("label", "")).strip()
        result.append({"id": calendar_id, "label": label})
    return result


def add_calendar_source(sources: list[dict], calendar_id: str, label: str) -> list[dict]:
    """Retourne une nouvelle liste avec l'entrée ajoutée (ou son label remplacé si l'ID existe déjà)."""
    calendar_id = (calendar_id or "").strip()
    if not calendar_id:
        raise ValueError("L'identifiant de calendrier ne peut pas être vide.")
    label = (label or "").strip()
    updated = [s for s in sources if s.get("id") != calendar_id]
    updated.append({"id": calendar_id, "label": label})
    return updated


def remove_calendar_source(sources: list[dict], calendar_id: str) -> list[dict]:
    """Retourne une nouvelle liste sans l'entrée dont l'ID correspond."""
    return [s for s in sources if s.get("id") != calendar_id]
