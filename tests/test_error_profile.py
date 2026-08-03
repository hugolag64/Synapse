import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    from backend.core.reviews import local_store

    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "errors.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def test_error_profile_groups_categories_and_counts():
    from backend.core.edn.error_profile import build_error_profile
    from backend.core.reviews import local_store

    local_store.insert_error_signal("221", "oubli", "2026-08-01", "qcm", "q-1", "indication")
    local_store.insert_error_signal("221", "oubli", "2026-08-02", "qcm", "q-2", "indication")
    local_store.insert_error_signal("221", "raisonnement", "2026-08-02", "qcm", "q-3", "diagnostic")

    profile = build_error_profile(item_number="221", days=30, store=local_store)

    assert profile["oubli"]["count"] == 2
    assert profile["oubli"]["evidence_ids"] == ["q-2", "q-1"]
    assert profile["raisonnement"]["count"] == 1


def test_error_profile_ignores_signals_outside_window():
    from backend.core.edn.error_profile import build_error_profile
    from backend.core.reviews import local_store

    local_store.insert_error_signal("221", "oubli", "2026-01-01", "qcm", "old", "ancienne")

    assert build_error_profile(item_number="221", days=30, store=local_store) == {}
