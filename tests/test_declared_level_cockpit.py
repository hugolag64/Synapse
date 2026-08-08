from pathlib import Path

COCKPIT_SOURCE = (
    Path(__file__).parents[1] / "frontend/pages/course_detail_cockpit.py"
).read_text(encoding="utf-8")


def _extract_function(source: str, name: str) -> str:
    """Renvoie le corps source d'une fonction top-level jusqu'à la prochaine
    définition top-level, sans importer le module (page NiceGUI, import évité
    par convention dans les tests de ce fichier)."""
    start = source.index(f"def {name}(")
    rest = source[start:]
    candidates = [i for i in (rest.find("\ndef ", 1), rest.find("\nasync def ", 1)) if i != -1]
    end = min(candidates) if candidates else len(rest)
    return rest[:end]


def test_declared_level_block_offers_the_three_levels_and_persists_them():
    body = _extract_function(COCKPIT_SOURCE, "_render_declared_level")
    assert '"solide"' in body
    assert '"correct"' in body
    assert '"flou"' in body
    assert "knowledge_store.set_item_state" in body
    assert "review_service.invalidate_cache" in body


def test_tab_overview_renders_declared_level_between_neighbors_and_reasons():
    body = _extract_function(COCKPIT_SOURCE, "_tab_overview")
    assert "_render_declared_level(course, mastery)" in body

    neighbors_idx = body.index("Notions reliées")
    declared_idx = body.index("_render_declared_level(course, mastery)")
    reasons_idx = body.index("Pourquoi ce score")

    assert neighbors_idx < declared_idx < reasons_idx
