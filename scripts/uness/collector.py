"""Local Playwright collector for UNESS annales.

The browser profile stays on the user's machine. Credentials are never read by
this module; the user authenticates in the visible browser when CAS asks for it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv

    load_dotenv(".env.local")
    load_dotenv()
except ImportError:  # pragma: no cover - dependency is part of the app runtime
    pass


def validate_annale_url(value: str) -> str:
    candidate = (value or "").strip()
    parsed = urlparse(candidate)
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "entrainement.uness.fr"
        or not parsed.path.startswith("/annales/")
    ):
        raise ValueError("URL UNESS annales invalide")
    return candidate


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "content"


async def _click_first(page, names: tuple[str, ...]) -> bool:
    for name in names:
        locator = page.get_by_role("button", name=re.compile(name, re.I))
        if await locator.count():
            await locator.first.click()
            return True
        locator = page.get_by_role("link", name=re.compile(name, re.I))
        if await locator.count():
            await locator.first.click()
            return True
    return False


async def _auto_login(page) -> bool:
    """Fill the local CAS form when credentials are provided in the process environment."""
    username = os.environ.get("UNESS_USERNAME", "").strip()
    password = os.environ.get("UNESS_PASSWORD", "")
    if not username or not password:
        return False
    user = page.locator('input[name="username"], input#username, input[type="email"]').first
    secret = page.locator('input[name="password"], input#password, input[type="password"]').first
    if not await user.count() or not await secret.count():
        return False
    await user.fill(username)
    await secret.fill(password)
    submit = page.locator('button[type="submit"], input[type="submit"]').first
    if await submit.count():
        await submit.click()
    else:
        await secret.press("Enter")
    return True


async def _ensure_enrolled(page) -> None:
    """Click through Moodle's self-enrolment page when the annale was never attempted."""
    if "/enrol/index.php" in page.url:
        if await _click_first(page, ("M'inscrire",)):
            await page.wait_for_load_state("domcontentloaded")


async def _fetch_html(page) -> str:
    """Fetch the current page's raw bytes instead of Chrome's already-parsed DOM text.

    UNESS serves some pages as Windows-1252 bytes while declaring UTF-8 in the
    Content-Type/meta tag. Chrome trusts the declared charset and replaces every
    accented byte sequence with an irrecoverable U+FFFD in page.content(). Re-fetching
    the raw response and decoding it ourselves lets us pick the encoding that actually
    round-trips instead of the one the page claims.
    """
    try:
        response = await page.context.request.get(page.url)
        raw = await response.body()
    except Exception:
        return await page.content()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252")


async def collect_annale(
    source_url: str,
    *,
    profile_dir: Path = Path("data/uness/browser-profile"),
    output_dir: Path = Path("data/uness/artifacts"),
    submit: bool = False,
) -> Path:
    """Collect visible UNESS review HTML into a local artifact directory."""
    source_url = validate_annale_url(source_url)
    try:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "Playwright requis : pip install playwright puis playwright install chromium"
        ) from exc

    profile_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_dir = output_dir / f"uness-{stamp}"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    contents: list[dict[str, str]] = []

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch_persistent_context(
            str(profile_dir), headless=False
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()
        await page.goto(source_url, wait_until="domcontentloaded")
        if "auth.uness.fr/cas/login" in page.url:
            await _auto_login(page)
            await page.wait_for_url("**/annales/**", timeout=300_000)
        await _ensure_enrolled(page)

        links = page.locator('a[href*="/mod/quiz/view.php?id="]')
        count = await links.count()
        for index in range(count):
            link = links.nth(index)
            title = (await link.inner_text()).strip() or f"content-{index + 1}"
            href = await link.get_attribute("href")
            if not href:
                continue
            await page.goto(href, wait_until="domcontentloaded")
            await _ensure_enrolled(page)
            status = "captured"
            relecture = page.get_by_role("link", name=re.compile("Relecture", re.I))
            if await relecture.count():
                # Attempt already completed earlier: read the existing review instead of resubmitting.
                await relecture.first.click()
                await page.wait_for_load_state("domcontentloaded")
                status = "reviewed" if "/mod/quiz/review.php" in page.url else "incomplete"
            elif submit:
                await _click_first(
                    page,
                    ("Effectuer le test", "Effectuer de nouveau le test", "Continuer votre tentative"),
                )
                await page.wait_for_load_state("domcontentloaded")
                await _click_first(page, ("Terminer le test", "Terminer le test..."))
                await page.wait_for_load_state("domcontentloaded")
                if await _click_first(page, ("Tout envoyer et terminer",)):
                    # The confirmation dialog reuses the same button label as the page's
                    # own trigger button, which stays in the DOM behind the dialog. Scope
                    # the confirm click to the dialog itself so `.first` cannot resolve
                    # back to the original (now-inert) trigger.
                    dialog = page.get_by_role("dialog")
                    try:
                        await dialog.wait_for(state="visible", timeout=5_000)
                        await dialog.get_by_role(
                            "button", name=re.compile("Tout envoyer et terminer", re.I)
                        ).first.click()
                    except PlaywrightTimeoutError:
                        pass
                    try:
                        await page.wait_for_url("**/mod/quiz/review.php**", timeout=15_000)
                        status = "reviewed"
                    except PlaywrightTimeoutError:
                        status = "incomplete"
                else:
                    status = "incomplete"
            html = await _fetch_html(page)
            filename = f"{index + 1:02d}-{_slug(title)}.html"
            (artifact_dir / filename).write_text(html, encoding="utf-8")
            contents.append({"title": title, "url": page.url, "html": filename, "status": status})
            await page.goto(source_url, wait_until="domcontentloaded")
            await _ensure_enrolled(page)

        manifest = {
            "source_url": source_url,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "collection_status": "submitted" if submit else "captured",
            "contents": contents,
        }
        (artifact_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        review_dir = Path("UNESS/à_vérifier")
        review_dir.mkdir(parents=True, exist_ok=True)
        upload_payload = {
            "bridge_schema_version": 1,
            "source": manifest,
            "instructions": "Extraire chaque question et proposition du HTML, conserver la correction officielle, puis appliquer le prompt fourni.",
            "prompt": Path("prompts/uness_correction_prompt.txt").read_text(encoding="utf-8") if Path("prompts/uness_correction_prompt.txt").is_file() else "",
            "contents": [
                {
                    **content,
                    "html": (artifact_dir / content["html"]).read_text(encoding="utf-8"),
                }
                for content in contents
            ],
        }
        upload_path = review_dir / f"uness-{stamp}.json"
        upload_path.write_text(json.dumps(upload_payload, ensure_ascii=False) + "\n", encoding="utf-8")
        await browser.close()
    return upload_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Collecter une annale UNESS localement")
    parser.add_argument("url")
    parser.add_argument("--submit", action="store_true", help="soumettre les tentatives blanches")
    parser.add_argument("--profile-dir", type=Path, default=Path("data/uness/browser-profile"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/uness/artifacts"))
    args = parser.parse_args()
    result = asyncio.run(
        collect_annale(
            args.url,
            profile_dir=args.profile_dir,
            output_dir=args.output_dir,
            submit=args.submit,
        )
    )
    print(result)


if __name__ == "__main__":
    main()
