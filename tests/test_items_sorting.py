from types import SimpleNamespace

from frontend.pages.items import _sort_item_rows, group_item_rows, visible_item_rows


def _row(item, title, colleges):
    return {"course": SimpleNamespace(item_number=item, title=title, college=colleges)}


def test_items_can_be_sorted_by_college_without_duplicate_rows():
    rows = [
        _row("2", "Deux", ["Pneumologie", "Cardiologie"]),
        _row("1", "Un", ["Cardiologie"]),
    ]

    sorted_rows = _sort_item_rows(rows, "college")

    assert [r["course"].title for r in sorted_rows] == ["Un", "Deux"]
    assert len(sorted_rows) == 2


def test_item_sort_keeps_numeric_item_order():
    rows = [_row("10", "Dix", ["A"]), _row("2", "Deux", ["A"])]

    assert [r["course"].title for r in _sort_item_rows(rows, "item")] == ["Deux", "Dix"]


def _full_row(item, title, colleges, level="maîtrisé", overdue=False):
    return {
        "course": SimpleNamespace(item_number=item, title=title, college=colleges),
        "mastery_level": level,
        "overdue": overdue,
    }


def test_priority_sort_orders_annual_priority_from_high_to_low():
    rows = [
        {**_full_row("3", "Basique", ["A"]), "ednpro_frequency": {"priority": "basique"}},
        {**_full_row("1", "Jamais", ["A"]), "ednpro_frequency": {"priority": "jamais_tombe"}},
        {**_full_row("4", "Indispensable", ["A"]), "ednpro_frequency": {"priority": "indispensable"}},
        {**_full_row("2", "Important", ["A"]), "ednpro_frequency": {"priority": "important"}},
    ]

    sorted_rows = _sort_item_rows(rows, "priority")

    assert [r["course"].title for r in sorted_rows] == [
        "Indispensable", "Important", "Basique", "Jamais",
    ]


def _filt(**overrides):
    base = {"mode": "all", "college": "Tous", "sort": "item"}
    base.update(overrides)
    return base


def test_visible_rows_apply_the_current_sort_mode():
    rows = [
        _full_row("2", "Deux", ["Pneumologie"]),
        _full_row("1", "Un", ["Cardiologie"]),
    ]

    by_item = visible_item_rows(rows, _filt(sort="item"))
    by_college = visible_item_rows(rows, _filt(sort="college"))

    assert [r["course"].title for r in by_item] == ["Un", "Deux"]
    assert [r["course"].title for r in by_college] == ["Un", "Deux"]


def test_switching_sort_mode_changes_the_rendered_order():
    rows = [
        _full_row("1", "Un", ["Pneumologie"]),
        _full_row("2", "Deux", ["Cardiologie"]),
    ]

    by_item = visible_item_rows(rows, _filt(sort="item"))
    by_college = visible_item_rows(rows, _filt(sort="college"))

    assert [r["course"].title for r in by_item] == ["Un", "Deux"]
    assert [r["course"].title for r in by_college] == ["Deux", "Un"]


def test_visible_rows_filter_on_selected_college():
    rows = [
        _full_row("1", "Un", ["Cardiologie"]),
        _full_row("2", "Deux", ["Pneumologie"]),
    ]

    visible = visible_item_rows(rows, _filt(college="Cardiologie", mode="college"))

    assert [r["course"].title for r in visible] == ["Un"]


def test_visible_rows_filter_on_fragile_and_overdue_modes():
    rows = [
        _full_row("1", "Un", ["A"], level="fragile"),
        _full_row("2", "Deux", ["A"], level="critique"),
        _full_row("3", "Trois", ["A"], level="maîtrisé", overdue=True),
    ]

    fragile = visible_item_rows(rows, _filt(mode="fragile"))
    overdue = visible_item_rows(rows, _filt(mode="overdue"))

    assert [r["course"].title for r in fragile] == ["Un", "Deux"]
    assert [r["course"].title for r in overdue] == ["Trois"]


def test_visible_rows_combine_college_and_status_mode():
    rows = [
        _full_row("1", "Fragile A", ["A"], level="fragile"),
        _full_row("2", "Solide A", ["A"], level="maîtrisé"),
        _full_row("3", "Fragile B", ["B"], level="fragile"),
    ]

    visible = visible_item_rows(rows, _filt(college="A", mode="fragile"))

    assert [r["course"].title for r in visible] == ["Fragile A"]


def test_items_list_is_not_capped_at_a_fixed_width():
    from pathlib import Path

    source = Path("frontend/pages/items.py").read_text(encoding="utf-8")

    assert ".it-wrap { max-width:none;" in source
    assert "max-width:1200px" not in source


def test_items_list_shows_counts_and_fiche_signal():
    from pathlib import Path

    source = Path("frontend/pages/items.py").read_text(encoding="utf-8")

    assert "items affichés" in source
    assert 'ui.label("FICHES")' in source
    assert 'r["type_tag"]' not in source


def test_college_sort_exposes_visible_groups_without_duplicate_items():
    rows = [
        _full_row("2", "Deux", ["Pneumologie"]),
        _full_row("1", "Un", ["Cardiologie"]),
        _full_row("3", "Trois", ["Cardiologie", "Pneumologie"]),
    ]

    groups = group_item_rows(rows)

    assert [name for name, _ in groups] == ["Cardiologie", "Pneumologie"]
    assert [[r["course"].title for r in group] for _, group in groups] == [
        ["Un", "Trois"],
        ["Deux"],
    ]
    assert sum(len(group) for _, group in groups) == len(rows)


def test_a_known_item_gets_planifier_instead_of_commencer():
    """Un item avec un score (déclaré ou mesuré) est déjà connu :
    « Commencer » mentirait en prétendant une première lecture aujourd'hui."""
    from pathlib import Path

    source = Path("frontend/pages/items.py").read_text(encoding="utf-8")

    assert 'r.get("mastery_score") is not None' in source
    assert "Planifier" in source
    assert "ne compte pas comme une première lecture" in source


def test_college_column_navigates_to_the_colleges_view():
    """La colonne COLLÈGE était du texte mort ; elle ouvre maintenant
    `/colleges` sur le collège principal de l'item, déplié (4.5)."""
    from pathlib import Path

    source = Path("frontend/pages/items.py").read_text(encoding="utf-8")

    assert 'f"/colleges?open={quote(name)}"' in source
    assert "it-college-link" in source


def test_college_column_shows_a_count_and_tooltip_instead_of_truncating():
    """50 items dépassent 60 caractères de libellés de collèges, tronqués
    sans indication par le line-clamp CSS (N18)."""
    from pathlib import Path

    source = Path("frontend/pages/items.py").read_text(encoding="utf-8")

    assert 'label_text += f" +{len(college_names) - 1}"' in source
    assert "college_label.tooltip(" in source


def test_college_sort_under_an_active_filter_labels_the_group_with_the_filtered_college():
    """Item 3 est multi-collèges (Cardiologie, Pneumologie) : son collège
    *principal* (premier alphabétique) est Cardiologie. Filtré sur
    Pneumologie et trié par collège, il apparaissait quand même sous le
    groupe « Cardiologie » — une étiquette qui ne correspond pas au filtre
    actif (N17)."""
    rows = [
        _full_row("2", "Deux", ["Pneumologie"]),
        _full_row("3", "Trois", ["Cardiologie", "Pneumologie"]),
    ]

    groups = group_item_rows(rows, "Pneumologie")

    assert [name for name, _ in groups] == ["Pneumologie"]
    assert [r["course"].title for r in groups[0][1]] == ["Deux", "Trois"]
