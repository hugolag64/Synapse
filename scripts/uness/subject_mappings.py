"""Medical subject mapping for UNESS course title normalization.

Maps various faculty naming conventions, abbreviations, and composite titles
to standardized EDN specialties.
"""

from __future__ import annotations

import re

# Standardized EDN Specialties & Category Keywords
SUBJECT_MAPPINGS: dict[str, dict[str, list[str]]] = {
    "Cardiovasculaire": {
        "canonical": "Cardiovasculaire",
        "aliases": [
            "cardio",
            "cardiologie",
            "cardiovasculaire",
            "appareil cardiovasculaire",
            "cardio-vasculaire",
            "cv",
            "vaisseaux",
        ],
    },
    "Hépato-Gastro-Entérologie": {
        "canonical": "Hépato-Gastro-Entérologie",
        "aliases": [
            "hge",
            "gastro",
            "gastro-enterologie",
            "gastroentérologie",
            "hepato-gastro",
            "hépato-gastro-entérologie",
            "appareil digestif",
            "digestif",
            "dig",
        ],
    },
    "Infectiologie": {
        "canonical": "Infectiologie",
        "aliases": [
            "infectiologie",
            "infectieux",
            "maladies infectieuses",
            "pi",
            "pathologies infectieuses",
            "infect",
        ],
    },
    "Neurologie": {
        "canonical": "Neurologie",
        "aliases": [
            "neurologie",
            "neuro",
            "neurochirurgie",
            "système nerveux",
            "neurologique",
        ],
    },
    "Pneumologie": {
        "canonical": "Pneumologie",
        "aliases": [
            "pneumologie",
            "pneumo",
            "appareil respiratoire",
            "respiratoire",
        ],
    },
    "Pédiatrie": {
        "canonical": "Pédiatrie",
        "aliases": [
            "pediatrie",
            "pédiatrie",
            "pedia",
            "pediatrique",
            "enfant",
            "santé de l'enfant",
        ],
    },
    "Gynécologie - Obstétrique": {
        "canonical": "Gynécologie - Obstétrique",
        "aliases": [
            "gyneco",
            "gynécologie",
            "obstetrique",
            "obstétrique",
            "go",
            "gyneco-obs",
            "gynecologie-obstetrique",
            "santé de la femme",
            "maieutique",
        ],
    },
    "Néphrologie": {
        "canonical": "Néphrologie",
        "aliases": [
            "nephrologie",
            "néphrologie",
            "nephro",
            "rein",
            "renal",
            "urologie-nephrologie",
        ],
    },
    "Urologie": {
        "canonical": "Urologie",
        "aliases": [
            "urologie",
            "uro",
            "appareil urinaire",
        ],
    },
    "Orthopédie - Traumatologie - Rhumatologie": {
        "canonical": "Orthopédie - Traumatologie - Rhumatologie",
        "aliases": [
            "rhumatologie",
            "rhumato",
            "orthopedie",
            "orthopédie",
            "traumatologie",
            "locomoteur",
            "appareil locomoteur",
            "ortho",
        ],
    },
    "Dermatologie": {
        "canonical": "Dermatologie",
        "aliases": [
            "dermato",
            "dermatologie",
            "peau",
        ],
    },
    "Endocrinologie - Diabétologie - Nutrition": {
        "canonical": "Endocrinologie - Diabétologie - Nutrition",
        "aliases": [
            "endocrinologie",
            "endocrino",
            "diabetologie",
            "nutrition",
            "metabolisme",
        ],
    },
    "Ophtalmologie": {
        "canonical": "Ophtalmologie",
        "aliases": [
            "ophtalmologie",
            "ophtalmo",
            "yeux",
            "vision",
        ],
    },
    "ORL - Chirurgie Cervico-Faciale": {
        "canonical": "ORL - Chirurgie Cervico-Faciale",
        "aliases": [
            "orl",
            "otolaryngologie",
            "cervico-faciale",
            "oto-rhino-laryngologie",
        ],
    },
    "Psychiatrie - Addictologie": {
        "canonical": "Psychiatrie - Addictologie",
        "aliases": [
            "psychiatrie",
            "psychiatrique",
            "psy",
            "addictologie",
            "sante mentale",
        ],
    },
    "Hématologie": {
        "canonical": "Hématologie",
        "aliases": [
            "hemato",
            "hématologie",
            "sang",
            "onco-hemato",
        ],
    },
    "Cancerologie - Oncologie": {
        "canonical": "Cancerologie - Oncologie",
        "aliases": [
            "cancerologie",
            "oncologie",
            "onco",
            "cancero",
            "tumeurs",
        ],
    },
    "Gériatrie": {
        "canonical": "Gériatrie",
        "aliases": [
            "geriatrie",
            "gériatrie",
            "vieillissement",
            "sujet agé",
            "personnes agées",
        ],
    },
    "Médecine d'urgence - Réanimation": {
        "canonical": "Médecine d'urgence - Réanimation",
        "aliases": [
            "urgences",
            "urgence",
            "reanimation",
            "réanimation",
            "soins intensifs",
            "urgentiste",
        ],
    },
}


def _normalize_text(text: str) -> str:
    """Strip accents and non-alphanumeric chars for robust matching."""
    text_lower = text.lower()
    text_no_accents = (
        text_lower.replace("é", "e")
        .replace("è", "e")
        .replace("ê", "e")
        .replace("à", "a")
        .replace("â", "a")
        .replace("ù", "u")
        .replace("û", "u")
        .replace("î", "i")
        .replace("ï", "i")
        .replace("ô", "o")
        .replace("ç", "c")
    )
    return text_no_accents


def match_subjects(title_or_breadcrumb: str) -> list[str]:
    """Find all canonical subjects matching a title or breadcrumb string."""
    normalized = _normalize_text(title_or_breadcrumb)
    matches: list[str] = []

    for canonical_name, config in SUBJECT_MAPPINGS.items():
        for alias in config["aliases"]:
            pattern = r"\b" + re.escape(_normalize_text(alias)) + r"\b"
            if re.search(pattern, normalized):
                if canonical_name not in matches:
                    matches.append(canonical_name)
                break

    return matches
