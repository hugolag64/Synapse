import asyncio


class _FakePage:
    def __init__(self, url: str, *, on_wait=None):
        self.url = url
        self._on_wait = on_wait
        self.waits = 0

    def is_closed(self):
        return False

    async def wait_for_timeout(self, _milliseconds: int):
        self.waits += 1
        if self._on_wait:
            self._on_wait()


class _FakeContext:
    def __init__(self, pages):
        self.pages = pages


def test_wait_for_ednpro_auth_accepts_authenticated_oauth_popup_result():
    from backend.core.ednpro.auth import wait_for_ednpro_auth

    popup = _FakePage("https://accounts.google.com/o/oauth2/auth")
    context = _FakeContext([popup])
    initial = _FakePage(
        "https://ednpro.app/auth",
        on_wait=lambda: context.pages.append(_FakePage("https://ednpro.app/annales")),
    )
    context.pages.append(initial)

    result = asyncio.run(wait_for_ednpro_auth(initial, context, timeout_ms=100))

    assert result.url == "https://ednpro.app/annales"
    assert popup.url.startswith("https://accounts.google.com")


def test_is_authenticated_ednpro_url_rejects_auth_and_external_pages():
    from backend.core.ednpro.auth import is_authenticated_ednpro_url

    assert not is_authenticated_ednpro_url("https://ednpro.app/auth")
    assert is_authenticated_ednpro_url("https://ednpro.app/annales")
    assert not is_authenticated_ednpro_url("https://accounts.google.com/")


def test_google_automation_rejection_is_classified_before_waiting_for_ednpro():
    from backend.core.ednpro.auth import GoogleAutomationRejected, wait_for_ednpro_auth

    rejected = _FakePage(
        "https://accounts.google.com/v3/signin/rejected?app_domain=https%3A%2F%2Foauth.lovable.app"
    )
    context = _FakeContext([rejected])

    try:
        asyncio.run(wait_for_ednpro_auth(rejected, context, timeout_ms=100))
    except GoogleAutomationRejected as exc:
        assert "Chrome normal" in str(exc)
    else:
        raise AssertionError("GoogleAutomationRejected attendu")
