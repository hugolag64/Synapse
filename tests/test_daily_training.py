"""Bloc « Entraînement du jour » : les deux entraînements quotidiens réunis.

Retour d'usage à l'origine de ce composant : Flash-Zéro et « Les 5 du jour »
étaient deux cartes sans lien visible, et la seconde annonçait
« Questions déjà disponibles · ITEM 147, ITEM 147 » — jargon interne et items
répétés.
"""
from pathlib import Path

from frontend.components.daily_training import MAX_LISTED_ITEMS, daily_queue_summary


def _rows(*item_numbers: str) -> list[dict]:
    return [{"item_number": n} for n in item_numbers]


def test_summary_dedupes_items_repeated_across_questions():
    """Le score de priorité est calculé par item : les 5 questions retenues
    viennent couramment du même item, ce qui donnait « ITEM 147 » cinq fois."""
    summary = daily_queue_summary(_rows("147", "147", "147", "147", "147"))

    assert summary["count"] == 5
    assert [item["number"] for item in summary["items"]] == ["147"]


def test_summary_names_items_by_their_edn_title():
    summary = daily_queue_summary(_rows("147"))

    assert "ITEM" not in summary["label"]
    assert summary["label"] == summary["items"][0]["title"]
    assert summary["items"][0]["title"].strip() != ""


def test_summary_falls_back_to_the_number_for_an_unknown_item():
    summary = daily_queue_summary(_rows("99999"))

    assert summary["label"] == "ITEM 99999"


def test_summary_truncates_a_long_list_and_keeps_the_full_one_for_the_tooltip():
    summary = daily_queue_summary(_rows("147", "221", "232", "245"))

    assert summary["label"].endswith(f"+{4 - MAX_LISTED_ITEMS}")
    assert summary["label"].count(",") == MAX_LISTED_ITEMS - 1
    assert summary["full_label"].count(",") == 3


def test_summary_handles_questions_without_any_item():
    summary = daily_queue_summary([{"item_number": ""}, {"item_number": None}])

    assert summary["count"] == 2
    assert summary["items"] == []
    assert summary["label"] == "Items non classés"


def test_block_names_both_trainings_and_says_where_questions_come_from():
    source = Path("frontend/components/daily_training.py").read_text(encoding="utf-8")

    assert "Entraînement du jour" in source
    assert "Pièges éliminatoires" in source
    assert "Tes questions en attente" in source
    assert "Tes erreurs récentes et répétées" in source
    assert "déjà dans ta base" in source
    # Le jargon interne remplacé par ce composant.
    assert "Questions déjà disponibles" not in source


def test_block_keeps_the_hover_dismiss_control_of_the_former_flash_zero_card():
    source = Path("frontend/components/daily_training.py").read_text(encoding="utf-8")

    assert ".dt-row:hover .dt-dismiss" in source
    assert "aria-label=" in source
    # La croix vit dans le flux, avant le bouton d'action : en position
    # absolue elle se retrouvait sous « Lancer » et n'était pas cliquable.
    assert "position:absolute" not in source
    assert source.index("dt-dismiss") < source.index('ui.button(action')


def test_block_renders_nothing_when_there_is_no_training_left():
    from frontend.components.daily_training import render_daily_training_block

    assert render_daily_training_block() is False


def test_today_view_renders_the_unified_block_instead_of_two_cards():
    source = Path("frontend/pages/dashboard/_cockpit_today.py").read_text(encoding="utf-8")

    assert "render_daily_training_block(" in source
    assert "render_flash_zero_card" not in source
    assert "Les 5 du jour" not in source
    assert "bg-indigo-50" not in source
