from types import SimpleNamespace
from pathlib import Path


def test_edn_insights_model_contains_progress_and_sprint_fields():
    from frontend.components.edn_insights_panel import edn_insights_model

    model = edn_insights_model(
        SimpleNamespace(
            days_remaining=73,
            target_date=SimpleNamespace(strftime=lambda _fmt: "15/10/2026"),
            phase=SimpleNamespace(value="consolidation"),
            covered_items=20,
            total_items=367,
            average_mastery=61.5,
            overdue_reviews=4,
            remaining_reviews=28,
            recommended_new_ratio=0.25,
            recommended_review_ratio=0.45,
            recommended_qcm_dp_ratio=0.30,
            daily_target_items=6,
            focus_message="🎯 Mode Consolidation : Entraînement QCM/DP quotidien et rattrapage des lacunes Rang A.",
        )
    )

    assert model["countdown"] == "J-73"
    assert model["coverage"] == "20/367"
    assert model["mastery"] == "61.5 %"
    assert model["overdue"] == "4"
    assert model["focus_message"] == "🎯 Mode Consolidation : Entraînement QCM/DP quotidien et rattrapage des lacunes Rang A."
    assert model["new_ratio"] == "25"
    assert model["review_ratio"] == "45"
    assert model["qcm_dp_ratio"] == "30"
    assert model["daily_target_items"] == "6"


def test_edn_insights_panel_renders_focus_message_and_ratio_breakdown():
    source = Path("frontend/components/edn_insights_panel.py").read_text(encoding="utf-8")
    start = source.index("def render_edn_insights_panel(")
    body = source[start:]

    assert 'model["focus_message"]' in body
    assert "model['new_ratio']" in body
    assert "model['review_ratio']" in body
    assert "model['qcm_dp_ratio']" in body
    assert "model['daily_target_items']" in body


def test_dashboard_reads_the_persisted_edn_target_date():
    source = Path("frontend/pages/dashboard/_cockpit_today.py").read_text(encoding="utf-8")

    assert 'preferences.get("edn_target_date", "2026-10-15")' in source


def test_sprint_visibility_is_persisted_and_hides_only_the_dashboard_card():
    dashboard = Path("frontend/pages/dashboard/_cockpit_today.py").read_text(encoding="utf-8")
    component = Path("frontend/components/edn_insights_panel.py").read_text(encoding="utf-8")

    assert 'preferences.get("edn_sprint_visible", True)' in dashboard
    assert 'set_preference("edn_sprint_visible", False)' in dashboard
    assert "on_hide=_hide_sprint" in dashboard
    assert "on_hide=None" in component
    assert 'ui.button("Masquer", on_click=on_hide)' in component


def test_streamlit_sprint_widget_is_gone():
    import subprocess

    widget_path = Path("frontend/components/sprint_countdown_widget.py")
    assert not widget_path.exists()

    result = subprocess.run(
        ["git", "grep", "-l", "render_sprint_countdown_widget", "--", "frontend", "backend"],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "", f"still referenced in: {result.stdout}"
