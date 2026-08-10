import asyncio
import inspect
import sys

import pytest


def test_extract_training_records_accepts_nested_api_response():
    from backend.core.ednpro.frequency_sync import extract_training_records

    records = extract_training_records({
        "data": {
            "cards": [
                {"item": "221", "priority": "Indispensable", "sessions": 3, "question_count": 10, "years": [2023, 2024]}
            ]
        }
    })

    assert records[0]["item"] == "221"


def test_build_complete_frequency_snapshot_fills_never_seen_items():
    from backend.core.ednpro.frequency_sync import build_complete_frequency_snapshot

    rows = build_complete_frequency_snapshot(
        [{
            "item_number": 247,
            "nb_sessions": 13,
            "nb_questions": 31,
            "annees": [2025, 2024, 2023, 2022],
        }],
        ["1", "247"],
        source_url="training-v2",
        collected_at="2026-08-10T10:27:04+00:00",
        expected_catalog_size=2,
    )

    assert rows[0]["priority"] == "jamais_tombe"
    assert rows[1]["session_count"] == 13


def test_build_complete_frequency_snapshot_rejects_duplicate_remote_items():
    from backend.core.ednpro.frequency_sync import build_complete_frequency_snapshot

    with pytest.raises(ValueError, match="duplicate"):
        build_complete_frequency_snapshot(
            [{"item_number": 247}, {"item_number": 247}],
            ["247"],
            source_url="training-v2",
            collected_at="2026-08-10T10:27:04+00:00",
            expected_catalog_size=1,
        )


def test_sync_from_annales_index_payload_persists_only_complete_snapshot(monkeypatch):
    from backend.core.ednpro import frequency_sync

    class Store:
        def __init__(self):
            self.rows = None

        def replace_ednpro_item_frequencies(self, rows):
            self.rows = rows

        def compare_latest_ednpro_frequency_snapshots(self):
            return []

    store = Store()
    monkeypatch.setattr(frequency_sync, "local_store", store)

    result = asyncio.run(
        frequency_sync.sync_from_annales_index_payload(
            [{
                "item_number": 247,
                "nb_sessions": 13,
                "nb_questions": 31,
                "annees": [2025, 2024, 2023, 2022],
            }],
            catalog_items=["1", "247"],
            source_url="training-v2",
            collected_at="2026-08-10T10:27:04+00:00",
            expected_catalog_size=2,
        )
    )

    assert result["status"] == "updated"
    assert len(store.rows) == 2
    assert store.rows[1]["session_count"] == 13
    assert store.rows[1]["question_count"] == 31


def test_sync_from_annales_index_payload_rejects_empty_response(monkeypatch):
    from backend.core.ednpro import frequency_sync

    store = type("Store", (), {"replace_ednpro_item_frequencies": lambda *_: pytest.fail("write")})()
    monkeypatch.setattr(frequency_sync, "local_store", store)

    with pytest.raises(ValueError, match="vide"):
        asyncio.run(
            frequency_sync.sync_from_annales_index_payload(
                [],
                catalog_items=["1"],
                source_url="training-v2",
                expected_catalog_size=1,
            )
        )


def test_fetch_annales_index_payload_returns_rpc_rows_without_token_material():
    from backend.core.ednpro import frequency_sync

    class Page:
        async def evaluate(self, script):
            assert "get_annales_items_index" in script
            assert "access_token" in script
            return [{"item_number": 247, "nb_sessions": 13, "nb_questions": 31, "annees": [2025]}]

    rows = asyncio.run(frequency_sync.fetch_annales_index_payload(Page()))

    assert rows == [{"item_number": 247, "nb_sessions": 13, "nb_questions": 31, "annees": [2025]}]


def test_sync_from_payload_does_not_replace_snapshot_on_empty_payload(monkeypatch):
    from backend.core.ednpro import frequency_sync

    class Store:
        def __init__(self):
            self.rows = [{"item_number": "221"}]
            self.replaced = False

        def get_ednpro_frequency_snapshot(self):
            return {"collected_at": "2026-01-01T00:00:00+00:00"}

        def replace_ednpro_item_frequencies(self, rows):
            self.replaced = True

    store = Store()
    monkeypatch.setattr(frequency_sync, "local_store", store)

    result = asyncio.run(
        frequency_sync.sync_from_payload({}, source_url="https://ednpro.app/training-v2")
    )

    assert result["status"] == "empty"
    assert store.replaced is False


def test_frequency_cli_forwards_cdp_url_for_normal_chrome(monkeypatch):
    from scripts.ednpro import frequency_collector

    captured = {}

    async def fake_sync_if_due(**kwargs):
        captured.update(kwargs)
        return {"status": "updated", "rows": 1}

    monkeypatch.setattr(frequency_collector, "sync_if_due", fake_sync_if_due)
    monkeypatch.setattr(
        sys,
        "argv",
        ["frequency_collector.py", "--force", "--cdp-url", "http://127.0.0.1:9222"],
    )

    frequency_collector.main()

    assert captured["cdp_url"] == "http://127.0.0.1:9222"


def test_frequency_sync_is_headless_by_default_on_server():
    from backend.core.ednpro import frequency_sync

    assert inspect.signature(frequency_sync.collect_frequency).parameters["headless"].default is True
    assert inspect.signature(frequency_sync.sync_if_due).parameters["headless"].default is True
    assert inspect.signature(frequency_sync.schedule_if_due).parameters["headless"].default is True
