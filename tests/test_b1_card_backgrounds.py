"""`--surface` est la couleur de survol, jamais un fond de repos. Deux traitements :
cartes individuellement cliquables (gardent leur :hover existant, seul le fond de
repos change) vs panneaux structurels (contiennent leurs propres lignes déjà
survolables : pas de nouveau :hover, sinon deux états de survol se superposent)."""
from pathlib import Path


def test_annale_lists_use_structural_rows_with_hover_state():
    annales = Path("frontend/pages/annales.py").read_text(encoding="utf-8")
    assert ".ans-exam-row {" in annales
    assert ".ans-exam-row:hover { background:var(--surface-hover); }" in annales

    annale_detail = Path("frontend/pages/annale_detail.py").read_text(encoding="utf-8")
    assert ".an-part-row {" in annale_detail
    assert ".an-part-row:hover { background:var(--surface-hover); }" in annale_detail


def test_structural_panels_rest_on_bg_without_a_new_hover_rule():
    qcm = Path("frontend/pages/qcm_cockpit.py").read_text(encoding="utf-8")
    history_rule = qcm.split(".qc-history {")[1].split("}")[0]
    selected_rule = qcm.split(".qc-selected {")[1].split("}")[0]
    assert "background:var(--surface);" not in history_rule
    assert "background:var(--bg);" in history_rule
    assert "background:var(--surface);" not in selected_rule
    assert "background:var(--bg);" in selected_rule
    assert ".qc-history:hover" not in qcm  # aucune nouvelle règle de survol ajoutée
    assert ".qc-selected:hover" not in qcm

    exam = Path("frontend/pages/exam_simulator_page.py").read_text(encoding="utf-8")
    assert ".ex-card { background:var(--bg);" in exam
    assert ".ex-panel-q { background:var(--bg);" in exam
    assert ".ex-card:hover" not in exam
    assert ".ex-panel-q:hover" not in exam
