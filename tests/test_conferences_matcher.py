from backend.core.conferences.matcher import match_college


def test_matches_via_known_abbreviation_table():
    result = match_college("MI")
    assert result.status == "matched"
    assert result.college_name == "Médecine Interne 🏥"


def test_matches_abbreviation_even_with_trailing_speaker_word():
    result = match_college("Psy CA")
    assert result.status == "matched"
    assert result.college_name == "Psychiatrie 🧩"


def test_matches_via_prefix_against_full_college_name():
    result = match_college("Cardio")
    assert result.status == "matched"
    assert result.college_name == "Cardiovasculaire ❤️"


def test_unrecognized_theme_needs_validation():
    result = match_college("Toussaint")
    assert result.status == "needs_validation"
    assert result.college_name is None


def test_short_unmatched_theme_needs_validation():
    result = match_college("OK")
    assert result.status == "needs_validation"


def test_ambiguous_prefix_across_multiple_colleges_needs_validation():
    result = match_college("Médecine")
    assert result.status == "needs_validation"
    assert result.college_name is None
