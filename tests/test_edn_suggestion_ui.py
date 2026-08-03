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
        "title": "Item 221 · oubli",
        "detail": "Erreur répétée : oubli (2 signal(s))",
        "evidence": "2 évidence(s)",
        "id": 7,
    }
