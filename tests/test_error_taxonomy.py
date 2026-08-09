from backend.core.edn.error_profile import map_discordance_to_error_category


def test_omission_on_rang_a_is_classified_as_rang_a():
    assert map_discordance_to_error_category(
        {"discordance": "omission", "rank": "A"}, {}, {}
    ) == "rang_a"


def test_excess_without_cognitive_context_is_explicitly_unclassified():
    assert map_discordance_to_error_category(
        {"discordance": "exces"}, {}, {}
    ) == "non_classe"


def test_explicit_piegedn_metadata_is_preserved():
    assert map_discordance_to_error_category(
        {"discordance": "exces", "error_category": "piege_edn"}, {}, {}
    ) == "piege_edn"
