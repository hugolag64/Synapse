from frontend.components.responsive_drawer import drawer_css_contract


def test_drawer_contract_exposes_expected_classes_and_breakpoint():
    contract = drawer_css_contract()

    assert contract["root"] == "synapse-responsive-drawer"
    assert contract["scrim"] == "synapse-responsive-drawer__scrim"
    assert contract["panel"] == "synapse-responsive-drawer__panel"
    assert contract["close"] == "synapse-responsive-drawer__close"
    assert contract["breakpoint"] == "(min-width: 900px) and (max-width: 1199.98px)"
