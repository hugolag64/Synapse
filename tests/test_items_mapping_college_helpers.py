from backend.core.qcm.items_mapping import abbreviation_to_college, all_college_names


def test_abbreviation_to_college_is_case_insensitive():
    assert abbreviation_to_college("mi") == "Médecine Interne 🏥"
    assert abbreviation_to_college("MI") == "Médecine Interne 🏥"


def test_abbreviation_to_college_returns_none_for_unknown_abbreviation():
    assert abbreviation_to_college("ZZZ") is None


def test_all_college_names_is_deduplicated_and_contains_known_colleges():
    names = all_college_names()
    assert names.count("Médecine légale - Santé publique ⚖️") == 1
    assert "Cardiovasculaire ❤️" in names
