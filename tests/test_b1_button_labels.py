"""Le préfixe « + » est redondant avec l'icône Quasar déjà affichée sur ces
boutons — retiré partout sauf sur le bouton mnémo/image (refonte complète prévue
au chantier B2, hors périmètre ici)."""
from pathlib import Path


def test_command_palette_buttons_drop_the_plus_prefix():
    source = Path("frontend/components/command_palette.py").read_text(encoding="utf-8")
    assert '"+ Lacune"' not in source
    assert '"+ QCM"' not in source
    assert '"+ Séance"' not in source
    assert '"Lacune"' in source
    assert '"QCM"' in source
    assert '"Séance"' in source


def test_course_quick_actions_reading_label_drops_the_plus_prefix():
    source = Path("frontend/components/course_quick_actions.py").read_text(encoding="utf-8")
    assert '"+ Lecture"' not in source
    assert '"label": "Lecture"' in source


def test_externat_new_stage_button_drops_the_plus_prefix():
    source = Path("frontend/pages/externat_cockpit.py").read_text(encoding="utf-8")
    assert '"+ Nouveau stage"' not in source
    assert '"Nouveau stage"' in source


def test_course_detail_uses_one_obsidian_action_and_linear_memo_label():
    source = Path("frontend/pages/course_detail_cockpit.py").read_text(encoding="utf-8")
    assert "💡 + Mnémo / Image" not in source
    assert 'ui.button("Ajouter un mémo", icon="add")' in source
    assert 'ui.button("Ouvrir dans Obsidian"' not in source
    assert "_btn_open =" not in source


def test_course_detail_prioritizes_training_tab_visually():
    source = Path("frontend/pages/course_detail_cockpit.py").read_text(encoding="utf-8")
    assert ".ci-tab-training" in source
    assert 'ui.tab("Entraînement").classes("ci-tab-training")' in source
