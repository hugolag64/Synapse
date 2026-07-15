"""Tests unitaires — resolve_college_folder() (backend/core/files.py)."""
from backend.core.files import resolve_college_folder


NOTION_COLLEGES = [
    "Cardiovasculaire ❤️",
    "Chirurgie digestive 🧵",
    "Chirurgie maxillo-faciale 🦷",
    "Endocrinologie - Diabétologie - Maladies métaboliques 🫘",
    "Infectiologie 🦠",
    "Neurochirurgie 🧠",
    "Neurologie 🧠",
    "Nutrition 🍔",
]


def test_correspondance_exacte_apres_normalisation():
    assert resolve_college_folder("Cardiovasculaire", NOTION_COLLEGES) == "Cardiovasculaire ❤️"


def test_correspondance_floue_avec_suffixe():
    assert resolve_college_folder("Infectiologie - Pilly", NOTION_COLLEGES) == "Infectiologie 🦠"


def test_correspondance_floue_avec_virgule_et_mots_en_moins():
    assert resolve_college_folder(
        "Endocrinologie, Diabétologie", NOTION_COLLEGES
    ) == "Endocrinologie - Diabétologie - Maladies métaboliques 🫘"


def test_override_pdf_college_mapping_prioritaire():
    assert resolve_college_folder(
        "Chirurgie générale viscérale et digestive", NOTION_COLLEGES
    ) == "Chirurgie digestive 🧵"


def test_neurochirurgie_ne_matche_pas_neurologie():
    assert resolve_college_folder("Neurochirurgie", NOTION_COLLEGES) == "Neurochirurgie 🧠"
    assert resolve_college_folder("Neurologie", NOTION_COLLEGES) == "Neurologie 🧠"


def test_dossier_non_resolu_retourne_none():
    assert resolve_college_folder("Anatomie", NOTION_COLLEGES) is None
    assert resolve_college_folder("Physiologie", NOTION_COLLEGES) is None


def test_faute_de_frappe_non_couverte_par_override_retourne_none():
    """Sans entrée dans PDF_COLLEGE_MAPPING, une faute de frappe reste non résolue
    plutôt que d'être mal classée par une correspondance floue trop permissive."""
    assert resolve_college_folder(
        "Chirurgie Générale Viscérale et Digetive", NOTION_COLLEGES
    ) is None
