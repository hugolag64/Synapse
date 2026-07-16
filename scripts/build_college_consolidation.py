"""
scripts/build_college_consolidation.py
----------------------------------------
Mapping propose (a valider) : les 59 colleges officiels UNESS/CNCEM
(acronyme -> nom nexternat) vers les 36 categories College existantes
dans Notion (consolidation many-to-one).

Ne touche pas a Notion. Sortie : data/college_consolidation.json
"""
from __future__ import annotations

import json
import os
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

NOTION_COLLEGES = [
    "Anatomie et cytologie pathologique\U0001F52C",
    "Anesthésie-Réanimation \U0001F489",
    "Cardiovasculaire ❤️",
    "Chirurgie digestive \U0001F9F5",
    "Chirurgie maxillo-faciale \U0001F9B7",
    "Dermatologie \U0001F9F4",
    "Douleur - Soins palliatifs \U0001F54A️",
    "Endocrinologie - Diabétologie - Maladies métaboliques \U0001FAD8",
    "Gynécologie médicale \U0001F338",
    "Gynécologie-Obstétrique \U0001F476",
    "Génétique \U0001F9EC",
    "Gériatrie \U0001F474",
    "Hématologie \U0001FA78",
    "Hépato-Gastro-entérologie \U0001F9FB",
    "Immunologie \U0001F489",
    "Infectiologie \U0001F9A0",
    "Médecine Intensive - Réanimation \U0001F6A8",
    "Médecine Interne \U0001F3E5",
    "Médecine générale \U0001FA7A",
    "Médecine légale - Santé publique ⚖️",
    "Médecine physique et réadaptation \U0001F9BF",
    "Neurochirurgie \U0001F9E0",
    "Neurologie \U0001F9E0",
    "Nutrition \U0001F354",
    "Néphrologie \U0001F9D1‍\U0001F52C",
    "ORL \U0001F442",
    "Oncologie \U0001F9EC",
    "Ophtalmologie \U0001F441️",
    "Orthopédie - Traumatologie \U0001F9B4",
    "Pneumologie \U0001FAC1",
    "Psychiatrie \U0001F9E9",
    "Pédiatrie \U0001F6BC",
    "Radiologie \U0001FA7B",
    "Rhumatologie \U0001F91D",
    "Thérapeutique \U0001F48A",
    "Urologie \U0001F6BB",
]

# acronyme UNESS -> categorie Notion (ou None si aucune categorie actuelle
# ne correspond -> item potentiellement non classe / a creer)
PROPOSED_MAPPING: dict[str, str | None] = {
    "CoPath": "Anatomie et cytologie pathologique\U0001F52C",
    "CNEAR": "Anesthésie-Réanimation \U0001F489",
    "CNECardio": "Cardiovasculaire ❤️",
    "CFCTCV": "Cardiovasculaire ❤️",
    "CEMV": "Cardiovasculaire ❤️",
    "CFCVE": "Cardiovasculaire ❤️",
    "CCVD": "Chirurgie digestive \U0001F9F5",
    "CNECMF": "Chirurgie maxillo-faciale \U0001F9B7",
    "CEDEF": "Dermatologie \U0001F9F4",
    "CEMD": "Douleur - Soins palliatifs \U0001F54A️",
    "CNEFUSP": "Douleur - Soins palliatifs \U0001F54A️",
    "CEEDMM": "Endocrinologie - Diabétologie - Maladies métaboliques \U0001FAD8",
    "CNEGM": "Gynécologie médicale \U0001F338",
    "CEGO": "Gynécologie-Obstétrique \U0001F476",
    "CBMDR": "Gynécologie-Obstétrique \U0001F476",
    "CNEPGM": "Génétique \U0001F9EC",
    "CNEG": "Gériatrie \U0001F474",
    "CEH": "Hématologie \U0001FA78",
    "CDUHGE": "Hépato-Gastro-entérologie \U0001F9FB",
    "ASSIM": "Immunologie \U0001F489",
    "CMIT": "Infectiologie \U0001F9A0",
    "AZAY": "Infectiologie \U0001F9A0",
    "ANOFEL": "Infectiologie \U0001F9A0",
    "CEMIR": "Médecine Intensive - Réanimation \U0001F6A8",
    "CNUMU": "Médecine Intensive - Réanimation \U0001F6A8",
    "CEMI": "Médecine Interne \U0001F3E5",
    "CNGE": "Médecine générale \U0001FA7A",
    "CNEML": "Médecine légale - Santé publique ⚖️",
    "CUESP": "Médecine légale - Santé publique ⚖️",
    "CIMES": "Médecine légale - Santé publique ⚖️",
    "COFEMER": "Médecine physique et réadaptation \U0001F9BF",
    "CENC": "Neurochirurgie \U0001F9E0",
    "CENeuro": "Neurologie \U0001F9E0",
    "CENutri": "Nutrition \U0001F354",
    "CUEN": "Néphrologie \U0001F9D1‍\U0001F52C",
    "ORL&CCF": "ORL \U0001F442",
    "CNECancer": "Oncologie \U0001F9EC",
    "COUF": "Ophtalmologie \U0001F441️",
    "CFCOT": "Orthopédie - Traumatologie \U0001F9B4",
    "CFECM": "Orthopédie - Traumatologie \U0001F9B4",
    "CNHUCP": "Orthopédie - Traumatologie \U0001F9B4",
    "CEP": "Pneumologie \U0001FAC1",
    "CNUP": "Psychiatrie \U0001F9E9",
    "CNPU": "Pédiatrie \U0001F6BC",
    "CERF": "Radiologie \U0001FA7B",
    "CNEBMN": "Radiologie \U0001FA7B",
    "COFER": "Rhumatologie \U0001F932",
    "CNET": "Thérapeutique \U0001F48A",
    "CNPM": "Thérapeutique \U0001F48A",
    "CFEU": "Urologie \U0001F6BB",
    # --- Decisions utilisateur (16/07/2026) sur les 9 colleges orphelins ---
    "CUNEA": "Psychiatrie \U0001F9E9",                       # Addictologie -> rattache a Psychiatrie
    "ANEBC": "Biologie Cellulaire \U0001F9EB",                # nouvelle categorie Notion (a creer)
    "CNBBMM": "Biochimie et Biologie Moléculaire \U0001F9EA",  # nouvelle categorie Notion (a creer)
    "CEHUMT": "Médecine du travail \U0001F9BA",                # nouvelle categorie Notion (a creer)
    "CEA": None,       # Allergologie -> pas de categorie dediee ; chaque item porteur
                        # (186, 187, 198) a deja un college sibling deja mappe (CEP/CEDEF/COFER)
    "CFEMTSEP": None,  # Medecine du sport -> idem, items 80 et 256 deja couverts par un sibling
    "CFCPRE": None,    # Chirurgie plastique reconstructive et esthetique -> ignore ("on s'en fiche")
    "COLHUM": None,    # Humanites -> ignore ("on tej") ; items 8,9,10,11,14 resteront sans college
    "CUMIC": None,     # Medecines Integratives et Complementaires -> non mentionne par l'utilisateur ;
                        # seul item porteur (327) deja couvert par CNET (Therapeutique) en relecture
}

# Nouvelles categories a creer dans le multi-select Notion "College"
NEW_NOTION_COLLEGES = [
    "Biologie Cellulaire \U0001F9EB",
    "Biochimie et Biologie Moléculaire \U0001F9EA",
    "Médecine du travail \U0001F9BA",
]


def main() -> None:
    nexternat = json.load(open(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "nexternat_items.json"),
        encoding="utf-8",
    ))
    acronyms = set(nexternat["colleges_by_acronym"].keys())
    mapped_acronyms = set(PROPOSED_MAPPING.keys())

    missing = acronyms - mapped_acronyms
    extra = mapped_acronyms - acronyms
    if missing:
        print(f"ERREUR : acronymes nexternat sans entree dans PROPOSED_MAPPING : {sorted(missing)}")
    if extra:
        print(f"ERREUR : acronymes dans PROPOSED_MAPPING absents de nexternat : {sorted(extra)}")

    unmapped = [a for a, v in PROPOSED_MAPPING.items() if v is None]
    print(f"{len(unmapped)} colleges officiels sans categorie Notion existante : {sorted(unmapped)}")

    out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "college_consolidation.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "notion_colleges": NOTION_COLLEGES + NEW_NOTION_COLLEGES,
            "new_notion_colleges": NEW_NOTION_COLLEGES,
            "mapping": PROPOSED_MAPPING,
            "nexternat_names": nexternat["colleges_by_acronym"],
        }, f, ensure_ascii=False, indent=2)
    print(f"Ecrit : {out_path}")


if __name__ == "__main__":
    main()
