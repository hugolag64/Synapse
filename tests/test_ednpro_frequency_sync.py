import asyncio


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
