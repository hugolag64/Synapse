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
    # Nom réel du dossier Drive (avec sa faute de frappe "Digetive"), couvert
    # explicitement par PDF_COLLEGE_MAPPING.
    assert resolve_college_folder(
        "Chirurgie Générale Viscérale et Digetive", NOTION_COLLEGES
    ) == "Chirurgie digestive 🧵"


def test_neurochirurgie_ne_matche_pas_neurologie():
    assert resolve_college_folder("Neurochirurgie", NOTION_COLLEGES) == "Neurochirurgie 🧠"
    assert resolve_college_folder("Neurologie", NOTION_COLLEGES) == "Neurologie 🧠"


def test_dossier_non_resolu_retourne_none():
    assert resolve_college_folder("Anatomie", NOTION_COLLEGES) is None
    assert resolve_college_folder("Physiologie", NOTION_COLLEGES) is None


def test_alias_dossier_vers_college_many_to_one():
    # PDF_COLLEGE_FOLDER_ALIASES permet à plusieurs dossiers de résoudre vers
    # le même collège sans affecter _get_college_folder (dossier canonique).
    assert resolve_college_folder("Chirurgie Vasculaire", NOTION_COLLEGES) == "Cardiovasculaire ❤️"
    assert resolve_college_folder("Médecine Infectieuse et Tropicale", NOTION_COLLEGES) == "Infectiologie 🦠"


def test_faute_de_frappe_non_couverte_par_override_retourne_none():
    """Sans entrée dans PDF_COLLEGE_MAPPING/PDF_COLLEGE_FOLDER_ALIASES, une faute
    de frappe reste non résolue plutôt que d'être mal classée par une
    correspondance floue trop permissive."""
    assert resolve_college_folder("Neurochirugie", NOTION_COLLEGES) is None
