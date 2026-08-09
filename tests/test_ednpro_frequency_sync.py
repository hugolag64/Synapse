import asyncio
import inspect
import sys


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
