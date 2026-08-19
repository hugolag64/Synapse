import asyncio
import datetime as dt

from backend.features import daily_routine


def test_daily_fac_sync_reads_j1_and_j2_and_keeps_routine_alive(monkeypatch):
    requested = []
    synced = []

    class FakeCalendar:
        async def get_events_for_day(self, day):
            requested.append(day)
            return [{"id": f"event-{day}", "summary": "Item 363"}]

    # The helper imports its collaborators lazily; patch their modules as well.
    import backend.core.google.calendar_service as calendar_module
    import backend.core.prep.service as prep_module
    monkeypatch.setattr(calendar_module, "calendar_service", FakeCalendar())
    monkeypatch.setattr(prep_module, "sync_fac_events", lambda *args, **kwargs: synced.append((args, kwargs)) or type("R", (), {"events_processed": 1, "tasks_created": 4})())

    asyncio.run(daily_routine._sync_fac_preparations(dt.date(2026, 8, 26)))

    assert requested == [dt.date(2026, 8, 27), dt.date(2026, 8, 28)]
    assert synced
    assert synced[0][1]["source_calendar_id"] == "kvj2875m68cng7oeiq6mbfh8k20ha1ru@import.calendar.google.com"
