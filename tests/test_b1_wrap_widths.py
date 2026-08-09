"""Les pages-liste du cockpit occupent toute la largeur disponible, sans plafond
artificiel — même correction qu'Items au chantier A."""
from pathlib import Path

_CAPPED_FILES = {
    "frontend/pages/qcm_cockpit.py": (".qc-wrap", "max-width:1200px"),
    "frontend/pages/annales.py": (".ans-wrap", "max-width:1200px"),
    "frontend/pages/annale_detail.py": (".an-wrap", "max-width:1200px"),
    "frontend/pages/exam_simulator_page.py": (".ex-wrap", "max-width:1100px"),
    "frontend/pages/prepa.py": (".prep-wrap", "max-width:980px"),
    "frontend/pages/revue.py": (".rh-wrap", "max-width:900px"),
    "frontend/pages/stats_cockpit.py": (".st-wrap", "max-width:900px"),
}


def test_list_pages_are_not_capped_at_a_fixed_width():
    for path, (_selector, old_cap) in _CAPPED_FILES.items():
        source = Path(path).read_text(encoding="utf-8")
        assert old_cap not in source, f"{path} still has {old_cap}"


def test_list_pages_declare_max_width_none():
    expectations = {
        "frontend/pages/qcm_cockpit.py": ".qc-wrap { width:100%; max-width:none;",
        "frontend/pages/annales.py": ".ans-wrap { width:100%; max-width:none;",
        "frontend/pages/annale_detail.py": ".an-wrap { width:100%; max-width:none;",
        "frontend/pages/exam_simulator_page.py": ".ex-wrap { width:100%; max-width:none;",
        "frontend/pages/prepa.py": ".prep-wrap { max-width:none;",
        "frontend/pages/revue.py": ".rh-wrap { max-width:none;",
        "frontend/pages/stats_cockpit.py": ".st-wrap { max-width:none;",
    }
    for path, expected in expectations.items():
        source = Path(path).read_text(encoding="utf-8")
        assert expected in source, f"{path} missing {expected!r}"


def test_weak_points_wrap_is_not_capped():
    source = Path("frontend/pages/weak_points_cockpit.py").read_text(encoding="utf-8")
    assert "width:860px" not in source
    assert ".wp-wrap { width:100%; max-width:none;" in source


def test_weekly_review_stretches_children_to_the_available_width():
    source = Path("frontend/pages/revue.py").read_text(encoding="utf-8")
    assert ".rh-wrap { max-width:none; width:100%; align-items:stretch; }" in source


def test_statistics_stretches_sections_and_their_rows():
    source = Path("frontend/pages/stats_cockpit.py").read_text(encoding="utf-8")
    assert ".st-wrap { max-width:none; width:100%; align-items:stretch; }" in source
    assert ".st-section { margin-bottom:24px; align-items:stretch; }" in source


def test_item_detail_center_column_reading_width_is_raised_not_removed():
    """Contrairement aux pages-liste (Task 1), la colonne centrale du détail
    d'item garde un plafond : elle contient du texte long (note Obsidian,
    paragraphes) qu'un plein-écran rendrait moins lisible. Décision utilisateur :
    plafond relevé (900 → 1100px), pas supprimé."""
    source = Path("frontend/pages/course_detail_cockpit.py").read_text(encoding="utf-8")
    assert "max-width:900px" not in source
    assert ".ci-center { flex:1 1 auto; min-width:0; max-width:1100px; }" in source
