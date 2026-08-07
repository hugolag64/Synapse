"""Les puces Activité, Durée, Confiance et Catégorie d'erreur n'utilisent plus
de couleurs Quasar arbitraires (indigo, rouge, orange, bleu, sarcelle, violet,
rose, orange foncé, gris-bleu) : elles passent à `primary`, seule couleur de
sélection sans signification propre. Difficulté et Résultat QCM, déjà corrects
(positive/warning/negative), ne sont pas touchés."""
import inspect

from frontend.pages.dashboard import _dialogs


def _source():
    return inspect.getsource(_dialogs.open_session_feedback_dialog)


def test_no_arbitrary_decorative_color_remains():
    source = _source()
    for color in (
        "indigo", "red", "orange", "deep-orange", "blue", "purple", "pink", "teal", "blue-grey",
    ):
        assert f'"{color}"' not in source, f"decorative color {color!r} still present"


def test_activity_and_duration_chips_use_primary():
    source = _source()
    assert '_chip_on("primary") if is_on else _chip_off()' in source
    # Les deux groupes (Activité et Durée) partagent ce même motif de construction.
    assert source.count('_chip_on("primary") if is_on else _chip_off()') == 2


def test_confidence_and_category_configs_use_primary():
    source = _source()
    assert '(1, "Très incertain", "primary")' in source
    assert '(2, "Incertain", "primary")' in source
    assert '(3, "Correct", "primary")' in source
    assert '(4, "Solide", "primary")' in source
    assert '(5, "Très solide", "primary")' in source
    assert '("diagnostic",             "Diagnostic",  "primary")' in source
    assert '("physiopathologie",       "Physiopath.", "primary")' in source
    assert '("autre",                  "Autre",       "primary")' in source


def test_difficulty_and_qcm_result_stay_semantic():
    """Non-régression : ces deux groupes encodent une vraie sémantique et ne
    doivent pas être touchés par la simplification des couleurs."""
    source = _source()
    assert 'DIFF_OPTS   = [("facile","Facile","positive"),("moyen","Moyen","warning"),("difficile","Difficile","negative")]' in source
    assert 'QCM_OPTS    = [(None,"—","grey"),("réussi","Réussi","positive"),("moyen","Moyen","warning"),("raté","Raté","negative")]' in source


def test_none_placeholder_in_error_categories_stays_grey():
    """L'option « aucune catégorie » n'est pas une catégorie décorative :
    elle garde son gris neutre."""
    source = _source()
    assert '(None,                     "—",           "grey")' in source
