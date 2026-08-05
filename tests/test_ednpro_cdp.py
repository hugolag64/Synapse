import asyncio
from pathlib import Path


def test_collector_can_attach_to_a_user_launched_chrome_over_cdp():
    from scripts.ednpro.collector import _open_ednpro_browser

    class Chromium:
        async def connect_over_cdp(self, url):
            assert url == "http://127.0.0.1:9222"
            return type("Browser", (), {"contexts": ["user-context"]})()

    playwright = type("Playwright", (), {"chromium": Chromium()})()

    connection, context, owns_context = asyncio.run(
        _open_ednpro_browser(playwright, Path("unused"), "http://127.0.0.1:9222")
    )

    assert connection.contexts == ["user-context"]
    assert context == "user-context"
    assert owns_context is False
