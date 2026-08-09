from backend.core.uness import exam_simulator


def test_imported_case_does_not_mark_every_proposition_as_rang_a(monkeypatch, tmp_path):
    from backend.core.reviews import local_store

    monkeypatch.setattr(
        local_store,
        "get_imported_practice_cases",
        lambda *, limit: [
            {
                "title": "DP test",
                "stem": "Un énoncé clinique suffisamment long pour être chargé comme un dossier progressif.",
                "kind": "DP",
                "item_numbers": ["115"],
                "questions": [
                    {
                        "prompt": "Question",
                        "choices": ["A", "B"],
                        "answer": "A",
                        "explanation": "Correction",
                    }
                ],
            }
        ],
    )
    monkeypatch.setattr(exam_simulator, "ARCHIVE_DIR", tmp_path)
    monkeypatch.setattr(exam_simulator, "AI_IMPORTS_DIR", tmp_path / "imports_ia")

    loaded = exam_simulator.load_dps_by_subject("CARDIOVASCULAIRE")

    assert [p["rank"] for p in loaded[0]["questions"][0]["propositions"]] == ["", ""]


def test_rang_a_detection_is_case_insensitive():
    score, mismatches = exam_simulator.compute_edn_score(
        {"a": False, "b": True},
        [
            {"id": "a", "reponse_uness": True, "rank": "a"},
            {"id": "b", "reponse_uness": False, "rank": "B"},
        ],
    )

    assert (score, mismatches) == (0.0, 2)
