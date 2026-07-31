"""Local Playwright collector for UNESS annales.

The browser profile stays on the user's machine. Credentials are never read by
this module; the user authenticates in the visible browser when CAS asks for it.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import mimetypes
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

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


def _stage_review_images(images_dir: Path, staging_dir: Path, review_dir: Path) -> list[str]:
    """Copy collected images into both the staging folder (cleaned up by
    import_service after import) and the review folder, alongside the bridge
    JSON — so both the manual ChatGPT/Gemini paste flow and the Gemini
    auto-correct button can find every image in one place without forgetting any."""
    if not images_dir.is_dir() or not any(images_dir.iterdir()):
        return []
    staging_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for image_file in sorted(images_dir.iterdir()):
        shutil.copy2(image_file, staging_dir / image_file.name)
        shutil.copy2(image_file, review_dir / image_file.name)
        copied.append(image_file.name)
    return copied


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


_IGNORED_IMAGE_PATTERN = re.compile(
    r"/theme/|/pix/|spacer\.(gif|png)|smiley|favicon|yui_combo", re.I
)

# Moodle's "qzone" (click-a-zone) question type doesn't put its background image in
# an <img> tag at all: the qzone-player.js widget embeds it as a base64 data URI
# inside an inline <script>, e.g. `const imageUrl = 'data:image/webp;base64,...'`.
_QZONE_IMAGE_PATTERN = re.compile(
    r"imageUrl\s*=\s*['\"]data:image/(?P<ext>[a-zA-Z0-9.+-]+);base64,(?P<data>[A-Za-z0-9+/=]+)['\"]"
)


def extract_question_images(html: str, base_url: str) -> list[dict[str, str]]:
    """Find real content images (dermato photos, radios, qzone scan crops...) inside
    each Moodle question container, skipping theme/UI icons. Plain <img> entries carry
    an "absolute_url" for the caller to download with an authenticated session; qzone's
    embedded images carry a ready-to-decode "data_uri" instead."""
    soup = BeautifulSoup(html, "html.parser")
    images: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for question_div in soup.select('div[id^="question-"]'):
        question_id = question_div.get("id", "")
        for img in question_div.find_all("img"):
            src = (img.get("src") or "").strip()
            if not src or _IGNORED_IMAGE_PATTERN.search(src):
                continue
            if src.startswith("data:"):
                # Some questions (DP/scanner images especially) embed the image
                # directly as a plain <img src="data:image/...;base64,...">, with
                # no pluginfile URL and no qzone <script> wrapper — decodable in
                # place, unlike an unrecognized/non-image data URI which we skip.
                if not src.startswith("data:image/") or ";base64," not in src:
                    continue
                if src in seen_urls:
                    continue
                seen_urls.add(src)
                images.append(
                    {
                        "question_id": question_id,
                        "data_uri": src,
                        "alt_text": (img.get("alt") or "").strip(),
                    }
                )
                continue
            absolute_url = urljoin(base_url, src)
            if absolute_url in seen_urls:
                continue
            seen_urls.add(absolute_url)
            images.append(
                {
                    "question_id": question_id,
                    "absolute_url": absolute_url,
                    "alt_text": (img.get("alt") or "").strip(),
                }
            )
        for script in question_div.find_all("script"):
            for match in _QZONE_IMAGE_PATTERN.finditer(script.get_text() or ""):
                images.append(
                    {
                        "question_id": question_id,
                        "data_uri": f"data:image/{match.group('ext')};base64,{match.group('data')}",
                        "alt_text": "",
                    }
                )
    return images


async def _download_question_images(
    page, html: str, base_url: str, images_dir: Path, quiz_slug: str
) -> list[dict[str, str]]:
    """Materialize images found in `html`: plain <img> ones are fetched via the
    authenticated Playwright session, qzone's embedded ones are just base64-decoded."""
    found = extract_question_images(html, base_url)
    downloaded: list[dict[str, str]] = []
    for index, image in enumerate(found, start=1):
        if "data_uri" in image:
            header, _, encoded = image["data_uri"].partition(",")
            try:
                body = base64.b64decode(encoded)
            except (ValueError, base64.binascii.Error):
                continue
            content_type = header.split(":", 1)[1].split(";", 1)[0] if ":" in header else ""
            extension = mimetypes.guess_extension(content_type) or ".webp"
        else:
            try:
                response = await page.context.request.get(image["absolute_url"])
                if not response.ok:
                    continue
                body = await response.body()
            except Exception:
                continue
            extension = (
                mimetypes.guess_extension(response.headers.get("content-type", "").split(";")[0].strip()) or ".bin"
            )
        filename = f"{quiz_slug}-{_slug(image['question_id'])}-{index}{extension}"
        images_dir.mkdir(parents=True, exist_ok=True)
        (images_dir / filename).write_bytes(body)
        downloaded.append(
            {
                "question_id": image["question_id"],
                # Relative to ARTIFACT_DIR (the parent of every "uness-<stamp>" run
                # folder) so `import_service.resolve_local_media_path` can find it
                # later — a bare "images/<file>" would miss the run subfolder.
                "filename": f"{images_dir.parent.name}/images/{filename}",
                "alt_text": image["alt_text"],
            }
        )
    return downloaded


async def collect_annale(
    source_url: str,
    *,
    profile_dir: Path = Path("data/uness/browser-profile"),
    output_dir: Path = Path("data/uness/artifacts"),
    submit: bool = False,
) -> list[Path]:
    """Collect visible UNESS review HTML into a local artifact directory.

    Writes one bridge JSON per quiz (not one bundled file for the whole course):
    a course can have several heavy quizzes, and handing the AI one bundle with
    all of them risks it truncating or hallucinating the heaviest one (seen in
    practice on a 4-quiz, ~600KB course). One file per quiz keeps each exchange
    small, and each is unambiguous to auto-match on import (see gemini_conversion).
    """
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
    images_dir = artifact_dir / "images"
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
            # Never trust an existing "Relecture" link: UNESS only keeps a completed
            # attempt's review browsable for 4 months ("La relecture d'une tentative
            # terminée est disponible pendant 4 mois."), but past that the link still
            # points at the same /mod/quiz/review.php URL — it just renders "La
            # tentative de test n'existe plus." there instead of real content, which
            # is indistinguishable from a real review by URL alone. Always take a
            # brand new attempt and read *that* review instead — it can never be
            # expired since it was just created.
            if submit:
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
            images = await _download_question_images(page, html, page.url, images_dir, _slug(title))
            contents.append(
                {"title": title, "url": page.url, "html": filename, "status": status, "images": images}
            )
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
        # Unique subfolder per collected exam session (e.g. UNESS/à_vérifier/session-20260731T141700Z/)
        subfolder_name = f"session-{stamp}"
        review_dir = Path("UNESS/à_vérifier") / subfolder_name
        review_dir.mkdir(parents=True, exist_ok=True)
        prompt_text = (
            Path("prompts/uness_correction_prompt.txt").read_text(encoding="utf-8")
            if Path("prompts/uness_correction_prompt.txt").is_file()
            else ""
        )
        upload_paths: list[Path] = []
        for content in contents:
            quiz_payload = {
                "bridge_schema_version": 1,
                "source": manifest,
                "instructions": "Extraire chaque question et proposition du HTML, conserver la correction officielle, puis appliquer le prompt fourni.",
                "prompt": prompt_text,
                "contents": [
                    {
                        **content,
                        "html": (artifact_dir / content["html"]).read_text(encoding="utf-8"),
                    }
                ],
            }
            quiz_path = review_dir / f"{_slug(content['title'])}-{stamp}.json"
            quiz_path.write_text(json.dumps(quiz_payload, ensure_ascii=False) + "\n", encoding="utf-8")
            upload_paths.append(quiz_path)
        await browser.close()
    staging_dir = Path("UNESS") / "images" / subfolder_name / stamp
    copied_images = _stage_review_images(images_dir, staging_dir, review_dir)
    if copied_images:
        names = ", ".join(path.name for path in upload_paths)
        print(
            f"Images trouvées : dossier {review_dir} prêt à corriger "
            f"(JSON + {len(copied_images)} image(s)) ({names})."
        )
    return upload_paths


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
    for path in result:
        print(path)


if __name__ == "__main__":
    main()
