from types import SimpleNamespace
from pathlib import Path


def test_settings_no_longer_exposes_manual_external_result_import():
    source = Path("frontend/pages/settings_cockpit.py").read_text(encoding="utf-8")

    assert "render_external_result_import" not in source
    assert "Contenu de l'export" not in source


def test_import_report_model_is_compact_and_explicit():
    from frontend.components.edn_insights_panel import import_report_model

    assert import_report_model(SimpleNamespace(accepted=3, updated=2, skipped=1, errors=({"message": "date"},))) == {
        "summary": "3 ajouté(s) · 2 mis à jour · 1 ignoré(s)",
        "errors": ["date"],
    }
