"""L'écran de lancement d'une session QCM générée par IA ne propose plus de
choisir la difficulté : seul l'EDN est préparé, le sélecteur n'a jamais d'utilité
réelle. L'enum PracticeDifficulty (backend) n'est pas touchée — elle sert au
service et à des tests indépendants de cet écran."""
import inspect

from frontend.components import ai_practice_panel


def test_generation_dialog_no_longer_builds_a_difficulty_toggle():
    source = inspect.getsource(ai_practice_panel._open_generation_dialog)
    assert "difficulty = ui.toggle(" not in source
    assert "PracticeDifficulty.STANDARD.value" not in source
    assert "PracticeDifficulty.DIFFICULT.value" not in source
    assert "PracticeDifficulty.CONCOURS.value" not in source


def test_generation_dialog_hardcodes_edn_difficulty():
    source = inspect.getsource(ai_practice_panel._open_generation_dialog)
    assert "difficulty=PracticeDifficulty.EDN," in source


def test_existing_generation_dialog_behavior_is_preserved():
    """Non-régression : le test déjà présent au chantier précédent continue de
    passer (comportement des sliders questions ouvertes/fermées inchangé)."""
    source = inspect.getsource(ai_practice_panel._open_generation_dialog)
    assert "value=0" in source
