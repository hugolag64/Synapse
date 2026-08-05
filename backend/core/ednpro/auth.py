"""Helpers for the visible EDNpro OAuth flow."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse


class GoogleAutomationRejected(RuntimeError):
    """Google rejected the automated browser before EDNpro authentication."""


def is_google_automation_rejection_url(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    return (
        parsed.netloc.lower().split(":", 1)[0] == "accounts.google.com"
        and parsed.path.rstrip("/").endswith("/signin/rejected")
    )


def is_authenticated_ednpro_url(url: str) -> bool:
    """Return whether *url* is an EDNpro page outside the login route."""
    parsed = urlparse(str(url or ""))
    host = parsed.netloc.lower().split(":", 1)[0]
    path = parsed.path.rstrip("/") or "/"
    return host in {"ednpro.app", "www.ednpro.app"} and path != "/auth"


async def wait_for_ednpro_auth(
    page: Any,
    context: Any,
    *,
    timeout_ms: int = 300_000,
    poll_ms: int = 250,
) -> Any:
    """Wait for any live context page to return to an authenticated EDNpro URL.

    Only URLs and page liveness are observed. Credentials, cookies, local
    storage and OAuth tokens remain entirely inside Chromium.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(0, timeout_ms) / 1000
    while True:
        for candidate in tuple(getattr(context, "pages", ())):
            if candidate.is_closed():
                continue
            if is_google_automation_rejection_url(candidate.url):
                raise GoogleAutomationRejected(
                    "Google a refusé le navigateur automatisé. Connecte-toi dans Chrome normal "
                    "puis relance la collecte via l'attachement Chrome."
                )
            if is_authenticated_ednpro_url(candidate.url):
                return candidate

        remaining_ms = int((deadline - loop.time()) * 1000)
        if remaining_ms <= 0:
            raise TimeoutError("Connexion Google EDNpro non terminée")
        await page.wait_for_timeout(min(max(1, poll_ms), remaining_ms))
