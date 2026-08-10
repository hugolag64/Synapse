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


def test_telemetry_success_and_danger_text_meet_contrast_in_both_themes():
    source = Path("frontend/pages/settings_cockpit.py").read_text(encoding="utf-8")

    for legacy in (
        ".se-tele-value { font-size:20px; font-weight:700; color:var(--success); }",
        ".se-tele-cost { font-family:var(--font-mono); font-weight:700; color:var(--success); flex:0 0 auto; }",
        ".se-tele-ok { font-family:var(--font-mono); font-weight:700; color:var(--success); flex:0 0 auto; }",
        ".se-tele-err { font-family:var(--font-mono); font-weight:700; color:var(--danger); flex:0 0 auto; }",
        "  color:var(--text-dim); font-weight:600; margin:14px 0 6px; }",
    ):
        assert legacy not in source, f"regle non lisible restante : {legacy}"

    for fixed in (
        ".se-tele-value { font-size:20px; font-weight:700; color:var(--success-text); }",
        ".se-tele-cost { font-family:var(--font-mono); font-weight:700; color:var(--success-text); flex:0 0 auto; }",
        ".se-tele-ok { font-family:var(--font-mono); font-weight:700; color:var(--success-text); flex:0 0 auto; }",
        ".se-tele-err { font-family:var(--font-mono); font-weight:700; color:var(--danger-text); flex:0 0 auto; }",
        "  color:var(--text-muted); font-weight:600; margin:14px 0 6px; }",
    ):
        assert fixed in source

    tokens_source = Path("frontend/design_tokens.py").read_text(encoding="utf-8")
    assert tokens_source.count("--success-text:") == 2
    assert tokens_source.count("--danger-text:") == 2
