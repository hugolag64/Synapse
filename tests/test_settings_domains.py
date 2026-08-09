from pathlib import Path


SOURCE = Path("frontend/pages/settings_cockpit.py").read_text(encoding="utf-8")


def test_settings_exposes_six_domain_expansions():
    for title in (
        "CONNEXIONS",
        "APPARENCE ET ACCESSIBILITÉ",
        "PLANIFICATION EDN",
        "DONNÉES UNESS",
        "LISA / OIC",
        "DIAGNOSTICS ET TÉLÉMÉTRIE",
    ):
        assert title in SOURCE
    assert SOURCE.count("_settings_domain(") >= 6
    assert "ui.expansion(" in SOURCE


def test_settings_domains_are_closed_by_default_and_share_one_group():
    assert "value=False" in SOURCE
    assert SOURCE.count("_settings_domain(") >= 6
    assert "group=" in SOURCE


def test_settings_keeps_existing_integrations_wired():
    for symbol in (
        "render_calendar_sources",
        "render_uness_diagnostics",
        "render_dp_coverage",
        "item_service.scrape_all_items",
    ):
        assert symbol in SOURCE


def test_settings_remains_full_width_and_responsive():
    assert ".se-wrap {" in SOURCE
    assert "width:100%" in SOURCE
    assert "max-width: 820px" in SOURCE


def test_settings_domain_order_matches_the_spec():
    titles = (
        "CONNEXIONS",
        "APPARENCE ET ACCESSIBILITÉ",
        "PLANIFICATION EDN",
        "DONNÉES UNESS",
        "LISA / OIC",
        "DIAGNOSTICS ET TÉLÉMÉTRIE",
    )
    positions = [SOURCE.index(title) for title in titles]
    assert positions == sorted(positions)


def test_settings_domain_descriptions_are_present():
    for description in (
        "Fournisseurs et calendriers",
        "Thème et préférences d'affichage",
        "Dates et Sprint EDN",
        "Import et normalisation",
        "Objectifs de connaissance",
        "Couverture et consommation",
    ):
        assert description in SOURCE
