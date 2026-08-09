def test_edn_suggestion_model_explains_action_and_evidence():
    from frontend.pages.weak_points_cockpit import edn_suggestion_model

    model = edn_suggestion_model({
        "id": 7,
        "item_number": "221",
        "category": "oubli",
        "detail": "Erreur répétée : oubli (2 signal(s))",
        "evidence_ids": ["q1", "q2"],
    })

    assert model == {
        "title": "Item 221 · Erreur d’oubli",
        "detail": "Erreur répétée · Oubli · 2 signaux",
        "evidence": "2 signaux sources",
        "id": 7,
    }


def test_edn_suggestion_model_makes_unclassified_repeated_errors_explicit():
    from frontend.pages.weak_points_cockpit import edn_suggestion_model

    model = edn_suggestion_model({
        "id": 8,
        "item_number": "93",
        "category": "non_classe",
        "detail": "Erreur répétée : non_classe (2 signal(s))",
        "evidence_ids": ["q1", "q2"],
    })

    assert model["title"] == "Item 93 · Erreur non classée"
    assert model["detail"] == "Erreur répétée · Non classée · 2 signaux"
    assert model["evidence"] == "2 signaux sources"
