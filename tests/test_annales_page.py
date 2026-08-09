"""Tests for the grouped Annales list page's filtering logic."""

from __future__ import annotations

import pytest

from backend.core.reviews import local_store


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def _seed_annale(source_url: str, matiere: str, faculte: str, annee: int, type_annale: str) -> int:
    return local_store.create_uness_annale(
        source_url=source_url,
        collected_at="2026-07-30T18:21:37+00:00",
        faculte=faculte,
        niveau="DFASM1",
        annee=annee,
        matiere=matiere,
        titre=f"Titre {matiere}",
        type_annale=type_annale,
    )


def test_annales_list_filters_by_matiere_faculte_annee_and_type() -> None:
    _seed_annale("url-1", "GÉRIATRIE", "Faculté de La Réunion", 2024, "matiere")
    _seed_annale("url-2", "NEUROLOGIE", "Faculté de Paris Saclay", 2025, "concours_blanc")

    from frontend.pages.annales import _filtered_annales

    assert len(_filtered_annales(matiere="GÉRIATRIE")) == 1
    assert len(_filtered_annales(faculte="Faculté de Paris Saclay")) == 1
    assert len(_filtered_annales(annee=2024)) == 1
    assert len(_filtered_annales(type_annale="concours_blanc")) == 1
    assert len(_filtered_annales()) == 2


def test_format_gemini_summary_reports_counts_and_estimated_cost() -> None:
    from frontend.pages.annales import _format_gemini_summary

    result = {
        "corrected": ["dp1-x.json", "kfp-x.json"],
        "errors": [],
        "input_tokens": 40_000,
        "output_tokens": 6_000,
    }

    summary = _format_gemini_summary(result)

    assert "2 quiz corrigé" in summary
    assert "0 erreur" in summary
    assert "40" in summary  # input token count, in thousands or raw form
    assert "$" in summary


def test_format_gemini_summary_reports_errors() -> None:
    from frontend.pages.annales import _format_gemini_summary

    result = {
        "corrected": [],
        "errors": [{"file": "dp1.json", "error": "Dossier introuvable"}],
        "input_tokens": 0,
        "output_tokens": 0,
    }

    summary = _format_gemini_summary(result)

    assert "0 quiz corrigé" in summary
    assert "1 erreur" in summary


def test_best_matiere_guess_matches_canonical_college_ignoring_emoji() -> None:
    from frontend.pages.annales import _best_matiere_guess

    candidates = ["Pneumologie 🫁", "Psychiatrie 🧩", "Cardiovasculaire ❤️"]

    assert _best_matiere_guess(candidates, "Pneumologie") == "Pneumologie 🫁"


def test_best_matiere_guess_returns_none_for_a_category_label_not_a_subject() -> None:
    """A breadcrumb category like "Entraînements examens DFASM2- T2 et T3" must
    never be guessed as a real subject just because it superficially resembles
    one — the dialog should fall back to "Autre" rather than pre-select a wrong
    college, which is exactly how unlinked, orphaned matières get created."""
    from frontend.pages.annales import _best_matiere_guess

    candidates = ["Pneumologie 🫁", "Psychiatrie 🧩", "Cardiovasculaire ❤️"]

    assert _best_matiere_guess(candidates, "Entraînements examens DFASM2- T2 et T3") is None


def test_format_failure_row_includes_title_attempts_and_reason() -> None:
    from frontend.pages.annales import _format_failure_row

    row = _format_failure_row(
        {"quiz_title": "SQI1\nTest", "attempts": 2, "error_message": "Extra data: line 42"}
    )

    assert "SQI1" in row
    assert "2 tentative" in row
    assert "Extra data: line 42" in row


def test_format_failure_row_singularizes_a_single_attempt() -> None:
    from frontend.pages.annales import _format_failure_row

    row = _format_failure_row({"quiz_title": "DP1", "attempts": 1, "error_message": "erreur"})

    assert "1 tentative " in row or row.count("tentatives") == 0


def test_gemini_partial_failure_message_is_none_when_everything_corrected() -> None:
    from frontend.pages.annales import _gemini_partial_failure_message

    result = {"corrected": ["dp1.json", "kfp1.json"], "errors": []}

    assert _gemini_partial_failure_message(result) is None


def test_gemini_partial_failure_message_surfaces_failed_quiz_even_when_others_succeeded() -> None:
    """This is the exact shape that used to vanish silently: 5 of 6 quizzes in
    a partiel correct fine (e.g. DP1/DP2/DP3/KFP1/mDP1), one (SQI1) fails —
    the caller must never treat this as a clean success."""
    from frontend.pages.annales import _gemini_partial_failure_message

    result = {
        "corrected": ["dp1.json", "dp2.json", "dp3.json", "kfp1.json", "mdp1.json"],
        "errors": [{"file": "sqi1.json", "error": "Extra data: line 42 column 3 (char 900)"}],
    }

    message = _gemini_partial_failure_message(result)

    assert message is not None
    assert "sqi1.json" in message
    assert "Extra data" in message


def test_annales_catalog_uses_stable_exam_columns_instead_of_cards() -> None:
    from pathlib import Path

    source = Path("frontend/pages/annales.py").read_text(encoding="utf-8")

    assert ".ans-exam-row" in source
    assert "grid-template-columns:minmax(240px, 1.4fr) 170px 150px 104px" in source
    assert "PROGRESSION" in source
    assert "SCORE OFFICIEL" in source


def test_annales_rows_stretch_to_the_catalog_width() -> None:
    from pathlib import Path

    source = Path("frontend/pages/annales.py").read_text(encoding="utf-8")

    assert ".ans-list { display:flex; flex-direction:column; gap:0; width:100%; align-items:stretch; }" in source


def test_displayable_annales_excludes_empty_group_rows():
    from frontend.pages.annales import _displayable_annales

    rows = [
        {"id": 1, "titre": "Test vide", "total_parts": 0},
        {"id": 2, "titre": "Épreuve importée", "total_parts": 8},
    ]

    assert [row["id"] for row in _displayable_annales(rows)] == [2]


def test_annales_are_grouped_into_edn_and_subject_families():
    from frontend.pages.annales import _group_annales_by_family

    groups = _group_annales_by_family([
        {"id": 1, "type_annale": "concours_blanc"},
        {"id": 2, "type_annale": "matiere"},
        {"id": 3, "type_annale": "edn"},
    ])

    assert [row["id"] for row in groups["EDN"]] == [1, 3]
    assert [row["id"] for row in groups["Matière"]] == [2]


def test_annales_family_filter_returns_only_the_selected_exam_family():
    from frontend.pages.annales import _filter_annales_by_family

    rows = [
        {"id": 1, "type_annale": "concours_blanc"},
        {"id": 2, "type_annale": "matiere"},
        {"id": 3, "type_annale": "edn"},
    ]

    assert [row["id"] for row in _filter_annales_by_family(rows, "EDN")] == [1, 3]
    assert [row["id"] for row in _filter_annales_by_family(rows, "Matière")] == [2]


def test_annales_catalog_uses_a_family_toggle():
    from pathlib import Path

    source = Path("frontend/pages/annales.py").read_text(encoding="utf-8")

    assert 'family_filter = ui.toggle' in source
    assert '"Épreuves EDN"' in source
    assert '"Épreuves par matière"' in source
