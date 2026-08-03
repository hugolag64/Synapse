import datetime

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    from backend.core.reviews import local_store

    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "external-results.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def test_csv_import_normalizes_rows_and_is_idempotent():
    from backend.core.edn.external_results import import_external_results, parse_external_results
    from backend.core.reviews import local_store

    payload = (
        "source,external_id,session_date,item_number,activity_type,score_percent\n"
        "EDNpro,r-1,2026-08-03,ITEM 221,QCM,62"
    )

    rows = parse_external_results(payload, "csv")
    assert rows == [
        rows[0].__class__(
            source="EDNpro",
            external_id="r-1",
            session_date=datetime.date(2026, 8, 3),
            item_number="221",
            activity_type="QCM",
            score_percent=62.0,
            total_questions=None,
            rank_a_percent=None,
            rank_b_percent=None,
            metadata={},
        )
    ]

    first = import_external_results(rows, store=local_store)
    second = import_external_results(rows, store=local_store)

    assert (first.accepted, first.updated, first.errors) == (1, 0, ())
    assert (second.accepted, second.updated, second.errors) == (0, 1, ())
    assert len(local_store.get_external_results()) == 1


def test_json_import_rejects_missing_required_item():
    from backend.core.edn.external_results import parse_external_results

    with pytest.raises(ValueError, match="item_number"):
        parse_external_results(
            '{"source":"Hypocampus","external_id":"h-1","session_date":"2026-08-03"}',
            "json",
        )
