"""
qcm/items_mapping.py — Synapse
-------------------------------
Mapping statique des 367 items EDN depuis data/items_edn.json.

Fournit :
  - item_title(item_number)   → titre officiel EDN (str)
  - item_college(item_number) → abréviation collège nexternat (str)
  - college_full(abbr)        → nom Notion complet (str)
  - resolve(item_number)      → (title, college_full) ou ("", "")
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA_PATH = Path(__file__).parent.parent.parent.parent / "data" / "items_edn.json"

# Abréviation nexternat → nom exact du multi_select "Collège" dans Notion (avec emoji).
# Source de vérité : options récupérées via l'API Notion (databases.retrieve).
# Note : SP et MTL sont fusionnés dans Notion sous un seul collège.
_ABBR_TO_NOTION: dict[str, str] = {
    "Psy":      "Psychiatrie 🧩",
    "MI":       "Médecine Interne 🏥",
    "SP":       "Médecine légale - Santé publique ⚖️",
    "MTL":      "Médecine légale - Santé publique ⚖️",
    "GO":       "Gynécologie-Obstétrique 👶",
    "Ped":      "Pédiatrie 🚼",
    "Gén":      "Génétique 🧬",
    "Oph":      "Ophtalmologie 👁️",
    "ORL":      "ORL 👂",
    "Neu":      "Neurologie 🧠",
    "Der":      "Dermatologie 🧴",
    "MPR":      "Médecine physique et réadaptation 🦿",
    "MG":       "Médecine générale 🩺",
    "Gér":      "Gériatrie 👴",
    "Uro":      "Urologie 🚻",
    "DSP":      "Douleur - Soins palliatifs 🕊️",
    "Inf":      "Infectiologie 🦠",
    "Thé":      "Thérapeutique 💊",
    "Imm":      "Immunologie 💉",
    "Pne":      "Pneumologie 🫁",
    "Hém":      "Hématologie 🩸",
    "End":      "Endocrinologie - Diabétologie - Maladies métaboliques 🫘",
    "Nut":      "Nutrition 🍔",
    "Nép":      "Néphrologie 🧑‍🔬",
    "HGE":      "Hépato-Gastro-entérologie 🧻",
    "Can":      "Oncologie 🧬",
    "MCV":      "Cardiovasculaire ❤️",
    "AR":       "Anesthésie-Réanimation 💉",
    "MIR":      "Médecine Intensive - Réanimation 🚨",
    "OT":       "Orthopédie - Traumatologie 🦴",
    "CMF":      "Chirurgie maxillo-faciale 🦷",
    "CD":       "Chirurgie digestive 🧵",
    "Rhu":      "Rhumatologie 🤲",
    "Générale": "Médecine générale 🩺",
}


@lru_cache(maxsize=1)
def _load() -> dict[int, dict]:
    """Charge le JSON et retourne un dict {item_number: {title, college}}."""
    try:
        items = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
        return {entry["item"]: entry for entry in items}
    except Exception:
        return {}


def _normalize_item(item_number: str | int) -> int | None:
    """Normalise un numéro d'item en int. Retourne None si invalide."""
    try:
        return int(float(str(item_number).strip()))
    except (ValueError, TypeError):
        return None


def item_title(item_number: str | int) -> str:
    """Retourne le titre officiel EDN de l'item, ou '' si inconnu."""
    n = _normalize_item(item_number)
    if n is None:
        return ""
    return _load().get(n, {}).get("title", "")


def item_college_abbr(item_number: str | int) -> str:
    """Retourne l'abréviation collège nexternat (ex: 'MCV', 'Inf'), ou ''."""
    n = _normalize_item(item_number)
    if n is None:
        return ""
    return _load().get(n, {}).get("college", "")


def college_full(abbr: str) -> str:
    """Abréviation → nom Notion exact (avec emoji). Ex: 'MCV' → 'Cardiovasculaire ❤️'."""
    return _ABBR_TO_NOTION.get(abbr) or ""


def resolve(item_number: str | int) -> tuple[str, str]:
    """
    Résout item_number → (titre_edn, nom_college_notion).
    Retourne ("", "") si item inconnu.
    """
    title = item_title(item_number)
    abbr  = item_college_abbr(item_number)
    return title, college_full(abbr)


def all_items() -> list[dict]:
    """Retourne la liste complète des 367 items avec {item, title, college}."""
    return list(_load().values())


def get_college_from_item(item_number: int | str) -> str | None:
    """
    Retourne le nom exact du collège Notion pour un item EDN (avec emoji).

    Retourne None si l'item est inconnu ou si l'abréviation n'a pas de collège
    Notion correspondant (ex: Thérapeutique).

    Exemple :
        get_college_from_item(228)  → "Cardiovasculaire ❤️"
        get_college_from_item("10") → "Médecine Interne 🏥"
    """
    abbr = item_college_abbr(item_number)
    if not abbr:
        return None
    return _ABBR_TO_NOTION.get(abbr) or None
