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

_ANNALES_INDEX_SCRIPT = r"""
async () => {
  const entryScript = Array.from(document.scripts)
    .map((script) => script.src)
    .find((src) => /\/assets\/index-[^/]+\.js$/.test(src));
  const bundleResponse = await fetch(entryScript || '/assets/index-BBaj_Hi8.js');
  const bundleText = await bundleResponse.text();
  const anonKey = (bundleText.match(/eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/) || [])[0] || '';
  const authStorageKey = Object.keys(localStorage).find(
    (key) => key.startsWith('sb-') && key.endsWith('-auth-token')
  );
  const rawAuth = authStorageKey ? localStorage.getItem(authStorageKey) : null;
  let accessToken = null;
  try {
    accessToken = rawAuth ? JSON.parse(rawAuth).access_token : null;
  } catch (_) {
    accessToken = null;
  }
  const projectMatch = authStorageKey && authStorageKey.match(/^sb-([^-]+)-auth-token$/);
  if (!anonKey || !accessToken || !projectMatch) {
    return { status: 401, data: null };
  }

  const response = await fetch(
    `https://${projectMatch[1]}.supabase.co/rest/v1/rpc/get_annales_items_index`,
    {
      method: 'POST',
      headers: {
        apikey: anonKey,
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json'
      },
      body: '{}'
    }
  );
  const responseText = await response.text();
  let data = null;
  try {
    data = JSON.parse(responseText);
  } catch (_) {
    data = null;
  }
  return { status: response.status, data };
}
"""


async def fetch_annales_index_payload(page: Any, *, retries: int = 3) -> list[dict]:
    """Fetch EDNpro's authenticated annales index without exposing its token."""
    last_error = "réponse inconnue"
    for attempt in range(max(1, int(retries))):
        try:
            result = await page.evaluate(_ANNALES_INDEX_SCRIPT)
        except Exception as exc:
            last_error = str(exc)
            result = None

        # Keeping this branch makes the helper easy to test with a page double,
        # while Chromium returns the status/data envelope from the script.
        if isinstance(result, list):
            if all(isinstance(row, dict) for row in result):
                return result
            last_error = "réponse contenant des lignes invalides"
        if isinstance(result, dict):
            status = int(result.get("status") or 0)
            data = result.get("data")
            if status == 200 and isinstance(data, list):
                if all(isinstance(row, dict) for row in data):
                    return data
                last_error = "réponse contenant des lignes invalides"
            if status in {401, 403}:
                raise RuntimeError("auth_required")
            last_error = f"statut HTTP {status}"

        if attempt + 1 < max(1, int(retries)):
            await asyncio.sleep(0.2)

    raise RuntimeError(f"get_annales_items_index indisponible: {last_error}")


def extract_training_records(payload: object) -> list[dict]:
    """Expose the row-like objects found in any JSON response shape."""
    from .frequency import _walk_rows

    return _walk_rows(payload)


def build_complete_frequency_snapshot(
    remote_rows: list[dict],
    catalog_items: list[dict | str | int],
    *,
    source_url: str,
    collected_at: str,
    expected_catalog_size: int = 367,
) -> list[dict]:
    """Build a complete item snapshot from EDNpro's annales index response."""
    catalog_numbers = [
        str(item.get("item") if isinstance(item, dict) else item).strip()
        for item in catalog_items
    ]
    if len(catalog_numbers) != expected_catalog_size or len(set(catalog_numbers)) != expected_catalog_size:
        raise ValueError(
            f"Le catalogue EDN doit contenir exactement {expected_catalog_size} items uniques"
        )

    remote_numbers = [str(row.get("item_number", "")).strip() for row in remote_rows]
    if any(not item for item in remote_numbers):
        raise ValueError("La réponse EDNpro contient un item invalide")
    if len(remote_numbers) != len(set(remote_numbers)):
        raise ValueError("La réponse EDNpro contient des items duplicate")

    normalized = normalize_training_payload(
        remote_rows, source_url=source_url, collected_at=collected_at
    )
    catalog_set = set(catalog_numbers)
    normalized_by_item = {row["item_number"]: row for row in normalized}
    unknown = set(normalized_by_item) - catalog_set
    if unknown:
        raise ValueError(f"La réponse EDNpro contient des items inconnus: {sorted(unknown)}")

    rows = []
    for item_number in sorted(catalog_numbers, key=lambda value: int(value)):
        rows.append(normalized_by_item.get(item_number, {
            "item_number": item_number,
            "priority": "jamais_tombe",
            "session_count": 0,
            "question_count": 0,
            "years": [],
            "source_url": source_url,
            "collected_at": collected_at,
        }))
    return rows


async def sync_from_annales_index_payload(
    payload: object,
    *,
    catalog_items: list[dict | str | int],
    source_url: str = TRAINING_URL,
    collected_at: str | None = None,
    expected_catalog_size: int = 367,
) -> dict:
    """Persist a validated complete snapshot from get_annales_items_index."""
    stamp = collected_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not isinstance(payload, list) or not payload:
        raise ValueError("La réponse EDNpro est vide ou invalide")
    if not all(isinstance(row, dict) for row in payload):
        raise ValueError("La réponse EDNpro contient des lignes invalides")
    remote_rows = payload
    rows = build_complete_frequency_snapshot(
        remote_rows,
        catalog_items,
        source_url=source_url,
        collected_at=stamp,
        expected_catalog_size=expected_catalog_size,
    )
    local_store.replace_ednpro_item_frequencies(rows)
    changes = local_store.compare_latest_ednpro_frequency_snapshots()
    return {"status": "updated", "rows": len(rows), "changed_items": len(changes), "collected_at": stamp}


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
    """Collect the authenticated annales index from training-v2."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Playwright requis pour la synchronisation EDNpro") from exc

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
            browser = context
            page = context.pages[0] if context.pages else await context.new_page()
        try:
            await page.goto(source_url, wait_until="domcontentloaded")
            if "/auth" in page.url:
                if headless:
                    return {"status": "auth_required", "rows": 0, "url": page.url}
                try:
                    page = await wait_for_ednpro_auth(page, browser)
                except TimeoutError:
                    return {"status": "auth_required", "rows": 0, "url": page.url}
            await page.wait_for_timeout(500)
            try:
                payload = await fetch_annales_index_payload(page)
            except RuntimeError as exc:
                if str(exc) == "auth_required":
                    return {"status": "auth_required", "rows": 0, "url": page.url}
                logger.warning(f"Collecte annales EDNpro indisponible : {exc}")
                return {"status": "empty", "rows": 0, "url": page.url}

            from backend.core.qcm.items_mapping import all_items

            try:
                return await sync_from_annales_index_payload(
                    payload,
                    catalog_items=all_items(),
                    source_url=source_url,
                )
            except ValueError as exc:
                logger.warning(f"Snapshot annales EDNpro invalide : {exc}")
                return {"status": "invalid", "rows": 0, "url": page.url, "error": str(exc)}
        finally:
            if owns_context:
                await context.close()


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
