from pathlib import Path


def test_settings_is_full_width_and_groups_domains_visually():
    source = Path("frontend/pages/settings_cockpit.py").read_text(encoding="utf-8")
    assert ".se-wrap { max-width:none; width:100%;" in source
    assert ".se-domain" in source
    assert "CONNEXIONS" in source
    assert "PLANIFICATION EDN" in source


def test_diagnostics_expansions_share_one_themed_style():
    source = Path("frontend/pages/settings_cockpit.py").read_text(encoding="utf-8")

    assert ".se-diag-expansion {" in source
    assert source.count('"w-full se-diag-expansion"') == 2


def test_telemetry_panel_uses_design_tokens_instead_of_frozen_slate():
    source = Path("frontend/pages/settings_cockpit.py").read_text(encoding="utf-8")

    for frozen in (
        "bg-slate-900/40",
        "bg-slate-800/50",
        "bg-slate-900/60",
        "border-slate-800",
        "border border-slate-700",
        "text-slate-200",
        "text-slate-300",
        "text-slate-400",
        "text-slate-500",
        "text-emerald-400",
        "text-red-400",
    ):
        assert frozen not in source, f"couleur figee restante : {frozen}"

    for token_class in (
        ".se-tele-kpis {",
        ".se-tele-value {",
        ".se-tele-strong {",
        ".se-tele-muted {",
        ".se-tele-section-title {",
        ".se-tele-list {",
        ".se-tele-row {",
        ".se-tele-cost {",
        ".se-tele-ok {",
        ".se-tele-err {",
    ):
        assert token_class in source
