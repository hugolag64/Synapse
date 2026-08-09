"""Smoke tests for the lazy OIC tab contract."""

from frontend.components.oic_panel import should_load_on_tab_activation
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_oic_tab_loads_only_when_activated_once():
    assert should_load_on_tab_activation("Vue d'ensemble", False) is False
    assert should_load_on_tab_activation("OIC", False) is True
    assert should_load_on_tab_activation("OIC", True) is False


def test_oic_panel_has_linear_summary_and_toolbar_contract():
    source = (ROOT / "frontend/components/oic_panel.py").read_text(encoding="utf-8")
    assert "Objectifs d’apprentissage" in source
    assert "Actualiser" in source
    assert "oic-panel-summary" in source


def test_oic_panel_keeps_explicit_evaluate_and_mastery_actions():
    source = (ROOT / "frontend/components/oic_panel.py").read_text(encoding="utf-8")
    assert "Évaluer cet OIC" in source
    assert "Basculer la maîtrise" in source


def test_oic_rows_use_a_stable_three_column_layout():
    source = (ROOT / "frontend/components/oic_panel.py").read_text(encoding="utf-8")
    assert "grid-template-columns:102px minmax(0,1fr) auto" in source
    assert "oic-row-status" in source
