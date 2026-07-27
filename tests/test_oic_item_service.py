"""Tests du modèle OIC canonique partagé entre les alias collège."""

import pytest

from backend.core.lisa import item_service


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    from backend.core.reviews import local_store

    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "oic.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def test_merges_alias_rows_by_oic_code_and_keeps_strongest_state():
    rows = [
        {
            "id": 1,
            "course_id": "mg",
            "oic_code": "OIC-75-01-A",
            "intitule": "A",
            "rang": "A",
            "ordre": 1,
            "mastered": 0,
            "oic_level": 1,
        },
        {
            "id": 2,
            "course_id": "psy",
            "oic_code": "OIC-75-01-A",
            "intitule": "A",
            "rang": "A",
            "ordre": 1,
            "mastered": 1,
            "oic_level": 3,
        },
        {
            "id": 3,
            "course_id": "psy",
            "oic_code": "OIC-75-02-B",
            "intitule": "B",
            "rang": "B",
            "ordre": 2,
            "mastered": 0,
            "oic_level": 0,
        },
    ]

    merged = item_service.merge_oic_rows(rows)

    assert [row["oic_code"] for row in merged] == [
        "OIC-75-01-A",
        "OIC-75-02-B",
    ]
    assert merged[0]["mastered"] == 1
    assert merged[0]["oic_level"] == 3
    assert merged[0]["source_ids"] == [1, 2]


def test_manual_mastery_propagates_to_all_alias_rows(monkeypatch):
    calls = []
    monkeypatch.setattr(
        item_service.local_store,
        "get_lisa_oic",
        lambda course_id: [
            {
                "id": 101 if course_id == "mg" else 102,
                "oic_code": "OIC-75-01-A",
                "mastered": 0,
            }
        ],
    )
    monkeypatch.setattr(
        item_service.local_store,
        "toggle_lisa_oic_mastery",
        lambda oid: calls.append(oid),
    )

    item_service.set_item_oic_mastery(["mg", "psy"], "OIC-75-01-A", True)

    assert calls == [101, 102]


def test_refresh_reconciliation_keeps_existing_identity_and_state():
    existing = [
        {"id": 17, "oic_code": "OIC-75-01-A", "mastered": 1, "oic_level": 3}
    ]
    incoming = [
        {
            "oic_code": "OIC-75-01-A",
            "intitule": "Updated",
            "rang": "A",
            "ordre": 1,
        }
    ]

    result = item_service.reconcile_oic_rows(existing, incoming)

    assert result[0]["id"] == 17
    assert result[0]["mastered"] == 1
    assert result[0]["oic_level"] == 3


def test_refresh_keeps_attempts_for_existing_oic_code():
    from backend.core.reviews import local_store

    oic = {
        "oic_code": "OIC-75-01-A",
        "intitule": "Initial",
        "rang": "A",
        "ordre": 1,
    }
    local_store.upsert_lisa_oic("psy", [oic])
    row = local_store.get_lisa_oic("psy")[0]
    local_store.update_oic_level(row["id"], 3)
    local_store.save_oic_attempt(row["id"], 85, "[]")

    local_store.upsert_lisa_oic(
        "psy",
        [{**oic, "intitule": "Updated"}],
    )

    refreshed = local_store.get_lisa_oic("psy")[0]
    assert refreshed["id"] == row["id"]
    assert refreshed["mastered"] == 1
    assert refreshed["oic_level"] == 3
    assert local_store.get_oic_attempts(refreshed["id"])[0]["session_score"] == 85


def test_evaluation_level_propagates_to_all_alias_rows(monkeypatch):
    from backend.core.reviews import local_store

    monkeypatch.setattr(
        local_store,
        "get_lisa_oic",
        lambda course_id: [{"id": 101 if course_id == "mg" else 102, "oic_code": "OIC-75-01-A"}],
    )
    calls = []
    monkeypatch.setattr(local_store, "update_oic_level", lambda oid, level: calls.append((oid, level)))

    item_service.set_item_oic_level(["mg", "psy"], "OIC-75-01-A", 4)

    assert calls == [(101, 4), (102, 4)]
