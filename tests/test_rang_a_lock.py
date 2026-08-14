"""Le verrou « Sécurité Rang A » ne doit pas punir le fait de commencer.

Aujourd'hui il s'arme dès la première tentative sur un objectif de rang A et
juge sur `réussis / total`, en comptant comme échecs les objectifs jamais
ouverts. Mesuré : trois cours ont un objectif tenté sur 13, 9 et 4, aucun
réussi — leur couverture vaut 0 % et les bloque en « fragile » de façon
quasi permanente. Sur une médiane de 8 objectifs par cours, ouvrir le premier
suffit à se condamner.

La règle retenue : le verrou ne s'arme qu'à partir d'un échantillon
représentatif, et juge alors sur ce qui a réellement été mesuré.
"""

from backend.core.knowledge.service import rang_a_verdict


def _cov(total, ok, attempted):
    return {"rang_a_total": total, "rang_a_ok": ok, "rang_a_attempted": attempted}


def test_a_single_attempt_on_a_long_list_is_not_conclusive():
    """Un objectif tenté sur 13 ne dit rien de la maîtrise du socle."""
    verdict = rang_a_verdict(_cov(13, 0, 1))

    assert verdict["conclusive"] is False
    assert verdict["pct"] is None


def test_three_attempts_make_the_verdict_conclusive():
    verdict = rang_a_verdict(_cov(13, 2, 3))

    assert verdict["conclusive"] is True
    assert verdict["pct"] == 2 / 3


def test_a_third_of_a_short_list_is_enough():
    """Sur 4 objectifs, en tenter 2 est déjà représentatif."""
    verdict = rang_a_verdict(_cov(4, 1, 2))

    assert verdict["conclusive"] is True
    assert verdict["pct"] == 0.5


def test_the_percentage_ignores_objectives_never_opened():
    """Le dénominateur est ce qui a été tenté, pas la liste entière : sinon
    allonger la liste d'objectifs dégrade mécaniquement le verdict."""
    court = rang_a_verdict(_cov(4, 3, 3))
    long = rang_a_verdict(_cov(19, 3, 3))

    assert court["pct"] == long["pct"] == 1.0


def test_no_attempt_at_all_is_not_conclusive():
    verdict = rang_a_verdict(_cov(9, 0, 0))

    assert verdict["conclusive"] is False
    assert verdict["pct"] is None


def test_an_item_without_rang_a_objectives_is_never_locked():
    verdict = rang_a_verdict(_cov(0, 0, 0))

    assert verdict["conclusive"] is False
    assert verdict["pct"] is None


def test_coverage_exposes_the_verdict():
    from backend.core.knowledge.service import oic_coverage
    import inspect

    source = inspect.getsource(oic_coverage)

    assert "rang_a_conclusive" in source
    assert "rang_a_pct_attempted" in source
