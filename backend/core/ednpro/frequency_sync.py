"""Playwright synchronisation of the EDNpro training frequency snapshot."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.core.reviews import local_store
from loguru import logger

from .auth import wait_for_ednpro_auth
from .frequency import is_frequency_sync_due, normalize_training_payload

TRAINING_URL = "https://ednpro.app/training-v2"
_running_task: asyncio.Task | None = None
_last_scheduled_at: datetime | None = None


def extract_training_records(payload: object) -> list[dict]:
    """Expose the row-like objects found in any JSON response shape."""
    from .frequency import _walk_rows

    return _walk_rows(payload)


async def sync_from_payload(
    payload: object,
    *,
    source_url: str = TRAINING_URL,
    collected_at: str | None = None,
) -> dict:
    stamp = collected_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    records = extract_training_records(payload)
    rows = normalize_training_payload(records, source_url=source_url, collected_at=stamp)
    if not rows:
        return {"status": "empty", "rows": 0, "collected_at": stamp}
    # Keep one bounded audit sample instead of duplicating a large response on
    # every item row.
    raw_payload = json.dumps(payload, ensure_ascii=False)[:100_000]
    for index, row in enumerate(rows):
        row["raw_payload_json"] = raw_payload if index == 0 else None
    local_store.replace_ednpro_item_frequencies(rows)
    changes = local_store.compare_latest_ednpro_frequency_snapshots()
    return {"status": "updated", "rows": len(rows), "changed_items": len(changes), "collected_at": stamp}


async def collect_frequency(
    *,
    profile_dir: Path = Path("data/ednpro/browser-profile"),
    source_url: str = TRAINING_URL,
    headless: bool = True,
    cdp_url: str | None = None,
) -> dict:
    """Collect JSON responses from training-v2 in a profile or normal Chrome."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Playwright requis pour la synchronisation EDNpro") from exc

    payloads: list[object] = []
    pending: list[asyncio.Task] = []
    tracked_pages: list[Any] = []

    async with async_playwright() as playwright:
        owns_context = cdp_url is None
        if cdp_url:
            browser = await playwright.chromium.connect_over_cdp(cdp_url)
            contexts = browser.contexts
            if not contexts:
                return {"status": "browser_unavailable", "rows": 0, "url": cdp_url}
            context = contexts[0]
            page = next((candidate for candidate in context.pages if "ednpro.app" in candidate.url), None)
            page = page or (context.pages[0] if context.pages else await context.new_page())
        else:
            profile_dir.mkdir(parents=True, exist_ok=True)
            context = await playwright.chromium.launch_persistent_context(str(profile_dir), headless=headless)
            page = context.pages[0] if context.pages else await context.new_page()

        async def consume(response: Any) -> None:
            try:
                data = await response.json()
            except Exception:
                return
            if isinstance(data, (dict, list)):
                payloads.append(data)

        def on_response(response: Any) -> None:
            content_type = str(response.headers.get("content-type", ""))
            if "json" in content_type:
                pending.append(asyncio.create_task(consume(response)))

        def track_page(target: Any) -> None:
            if target in tracked_pages:
                return
            target.on("response", on_response)
            tracked_pages.append(target)

        track_page(page)
        try:
            await page.goto(source_url, wait_until="domcontentloaded")
            if "/auth" in page.url:
                if headless:
                    return {"status": "auth_required", "rows": 0, "url": page.url}
                try:
                    page = await wait_for_ednpro_auth(page, browser)
                    track_page(page)
                except TimeoutError:
                    return {"status": "auth_required", "rows": 0, "url": page.url}
            await page.wait_for_timeout(2500)
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        finally:
            for tracked_page in tracked_pages:
                tracked_page.remove_listener("response", on_response)
            if owns_context:
                await context.close()

    if not payloads:
        return {"status": "empty", "rows": 0}
    return await sync_from_payload(payloads, source_url=source_url)


async def sync_if_due(
    *,
    profile_dir: Path = Path("data/ednpro/browser-profile"),
    force: bool = False,
    headless: bool = True,
    cdp_url: str | None = None,
) -> dict:
    snapshot = local_store.get_ednpro_frequency_snapshot()
    if not force and not is_frequency_sync_due(snapshot.get("collected_at") if snapshot else None):
        return {"status": "not_due", "rows": int(snapshot.get("item_count", 0)) if snapshot else 0}
    return await collect_frequency(profile_dir=profile_dir, headless=headless, cdp_url=cdp_url)


def schedule_if_due(
    *,
    profile_dir: Path = Path("data/ednpro/browser-profile"),
    headless: bool = True,
) -> bool:
    """Schedule at most one due collection, without blocking the background loop."""
    global _last_scheduled_at, _running_task
    if _running_task is not None and not _running_task.done():
        return False
    now = datetime.now(timezone.utc)
    if _last_scheduled_at is not None and now - _last_scheduled_at < timedelta(days=1):
        return False
    snapshot = local_store.get_ednpro_frequency_snapshot()
    if snapshot and not is_frequency_sync_due(snapshot.get("collected_at")):
        return False
    _last_scheduled_at = now
    _running_task = asyncio.create_task(
        sync_if_due(profile_dir=profile_dir, headless=headless)
    )
    _running_task.add_done_callback(_log_completed_task)
    return True


def _log_completed_task(task: asyncio.Task) -> None:
    try:
        result = task.result()
    except Exception as exc:
        logger.warning(f"Synchronisation fréquences EDNpro échouée : {exc}")
    else:
        logger.info(f"Synchronisation fréquences EDNpro terminée : {result}")
