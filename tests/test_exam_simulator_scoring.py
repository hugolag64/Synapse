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


def _props(*specs):
    return [
        {"id": pid, "reponse_uness": correct, "rank": rank}
        for pid, correct, rank in specs
    ]


def test_both_engines_agree_on_the_discordance_ladder():
    """Deux moteurs revendiquaient « le barème officiel » avec des règles
    différentes : la même réponse pouvait donner deux notes selon qu'on
    s'entraînait en mode standard ou en mode concours."""
    from backend.core.practice.scoring import compute_question_score_edn

    propositions = _props(("a", True, ""), ("b", True, ""), ("c", False, ""), ("d", False, ""))
    expected = {"a", "b"}

    for selected, awaited in (
        ({"a", "b"}, 1.0),
        ({"a"}, 0.5),
        ({"a", "c"}, 0.2),
        ({"c", "d"}, 0.0),
    ):
        user_choices = {p["id"]: (p["id"] in selected) for p in propositions}
        simulator_score, _ = exam_simulator.compute_edn_score(user_choices, propositions)
        canonical = compute_question_score_edn(selected, expected, question_kind="QRM")

        assert simulator_score == awaited
        assert canonical["score"] == awaited
        assert simulator_score == canonical["score"]


def test_simulator_delegates_to_the_single_scoring_engine():
    """Le simulateur ne doit plus reimplémenter le barème."""
    import inspect

    source = inspect.getsource(exam_simulator.compute_edn_score)

    assert "compute_question_score_edn" in source
    assert "mismatches == 1" not in source


def test_omitted_rang_a_still_cancels_the_question():
    score, discordances = exam_simulator.compute_edn_score(
        {"a": False, "b": True},
        _props(("a", True, "A"), ("b", True, "")),
    )

    assert score == 0.0
    assert discordances == 1
