import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    from backend.core.reviews import local_store

    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "gaps.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def test_repeated_same_category_produces_one_explainable_suggestion():
    from backend.core.edn.gap_suggestions import suggest_gap_candidates
    from backend.core.reviews import local_store

    local_store.insert_error_signal("221", "oubli", "2026-08-01", "qcm", "q-1", "indication")
    local_store.insert_error_signal("221", "oubli", "2026-08-02", "qcm", "q-2", "indication")

    suggestions = suggest_gap_candidates(item_number="221", store=local_store)

    assert len(suggestions) == 1
    assert suggestions[0]["category"] == "oubli"
    assert suggestions[0]["evidence_ids"] == ["q-2", "q-1"]


def test_one_signal_does_not_produce_a_gap_suggestion():
    from backend.core.edn.gap_suggestions import suggest_gap_candidates
    from backend.core.reviews import local_store

    local_store.insert_error_signal("221", "oubli", "2026-08-02", "qcm", "q-1", "indication")

    assert suggest_gap_candidates(item_number="221", store=local_store) == []


def test_accept_gap_suggestion_uses_stable_synthetic_course_id():
    from backend.core.edn.gap_suggestions import accept_gap_suggestion

    calls = {}

    class Store:
        def get_edn_recommendation(self, suggestion_id):
            return {
                "id": suggestion_id,
                "item_number": "93",
                "category": "non_classe",
                "detail": "Erreur répétée",
            }

        def add_weak_point_full(self, **kwargs):
            calls.update(kwargs)
            return 11

        def update_edn_recommendation(self, suggestion_id, status):
            calls["status"] = status

    assert accept_gap_suggestion(4, store=Store()) == 11
    assert calls["course_id"] == "item:93"
    assert calls["item_number"] == "93"
