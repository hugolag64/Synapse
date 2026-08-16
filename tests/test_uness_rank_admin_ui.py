from pathlib import Path


def test_rank_job_summary_exposes_the_five_operational_counters():
    from frontend.components.uness_rank_admin import summarize_rank_jobs

    summary = summarize_rank_jobs(
        [
            {"status": "pending"},
            {"status": "running"},
            {"status": "needs_oic"},
            {"status": "needs_admin"},
            {"status": "approved"},
            {"status": "rejected"},
        ]
    )

    assert summary == {
        "a_traiter": 2,
        "en_cours": 1,
        "sans_oic": 1,
        "incertains": 1,
        "resolus": 1,
    }


def test_rank_admin_component_contains_safe_source_labels_and_actions():
    source = Path("frontend/components/uness_rank_admin.py").read_text(encoding="utf-8")

    assert "RANGS UNESS — VALIDATION" in source
    assert "À traiter" in source
    assert "Sans OIC" in source
    assert "Gemini" in source
    assert "Officiel" in source
    assert "Admin" in source
    assert "Accepter Gemini" in source
    assert "Choisir A" in source
    assert "Choisir B" in source
    assert "Rejeter" in source
    assert "Relancer" in source


def test_settings_mounts_rank_admin_panel():
    source = Path("frontend/pages/settings_cockpit.py").read_text(encoding="utf-8")

    assert "render_uness_rank_admin" in source
    assert "RANGS UNESS — VALIDATION" in source
