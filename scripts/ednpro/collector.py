"""Visible, resumable EDNpro collector.

The first run asks the user to complete Google login in the visible persistent
browser profile. Once a source payload is captured, the same command can call
Gemini, write canonical JSON, and import it into Synapse.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from backend.core.ednpro.ai_pipeline import generate_and_import_ednpro
from backend.core.ednpro.collector import (
    _item_numbers,
    normalize_stable_resource_url,
    parse_annale_links,
    parse_video_cards,
)
from backend.core.uness import import_service


def _year(text: str, fallback: int) -> int:
    match = re.search(r"\b(20\d{2})\b", text or "")
    return int(match.group(1)) if match else fallback


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "ednpro"


def _boolean_attribute(value: Any) -> bool | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "oui", "correct", "vrai"}:
        return True
    if normalized in {"false", "0", "no", "non", "incorrect", "faux"}:
        return False
    return None


def extract_exam_payload(
    html: str,
    *,
    url: str,
    title: str,
    year: int,
    session_id: str,
    resources: list[dict] | None = None,
) -> dict:
    """Extract structured source answers from common EDNpro question markup."""
    soup = BeautifulSoup(html, "html.parser")
    containers = soup.select("[data-question-id], article.question, .question-card, [data-question]")
    questions: list[dict] = []
    seen: set[str] = set()
    for index, container in enumerate(containers, start=1):
        question_id = str(
            container.get("data-question-id")
            or container.get("data-question")
            or f"ednpro-q-{index}"
        )
        if question_id in seen:
            continue
        seen.add(question_id)
        stem_node = container.select_one("[data-question-stem], .question-stem, .question-text, .stem, h3, h4")
        stem = stem_node.get_text(" ", strip=True) if stem_node else container.get_text(" ", strip=True)
        choice_nodes = container.select("[data-choice-id], label.choice, .choice, .proposition")
        if not choice_nodes:
            choice_nodes = container.select("label")
        choices = []
        for choice_index, choice in enumerate(choice_nodes, start=1):
            choice_id = str(choice.get("data-choice-id") or choice.get("data-id") or f"{question_id}-p{choice_index}")
            correct = _boolean_attribute(choice.get("data-correct"))
            if correct is None:
                correct = _boolean_attribute(choice.get("aria-checked"))
            if correct is None:
                classes = " ".join(choice.get("class", []))
                correct = True if "correct" in classes.lower() else False if "incorrect" in classes.lower() else None
            choices.append({"id": choice_id, "text": choice.get_text(" ", strip=True), "correct": correct})
        item_numbers = _item_numbers(" ".join([
            f"Item {container.get('data-item-number', '')}",
            stem,
            str(container.get("aria-label", "")),
        ]))
        questions.append({
            "id": question_id,
            "type": str(container.get("data-question-type", "")),
            "stem": stem,
            "choices": choices,
            "item_numbers": item_numbers,
        })
    return {
        "title": title,
        "year": year,
        "session_id": session_id,
        "exam_id": session_id,
        "url": normalize_stable_resource_url(url),
        "subject": "",
        "questions": questions,
        "resources": resources or [],
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "collection_status": "captured",
    }


async def collect_ednpro(
    *,
    start_year: int = 2023,
    end_year: int | None = None,
    profile_dir: Path = Path("data/ednpro/browser-profile"),
    output_dir: Path = Path("data/ednpro/artifacts"),
    auto_correct: bool = True,
    service: Any = None,
) -> Path:
    """Collect eligible annales, optionally correct them with Gemini and import them."""
    try:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Playwright requis : pip install playwright puis playwright install chromium") from exc

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(output_dir) / f"ednpro-{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    profile_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "source": "EDNpro",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "start_year": start_year,
        "end_year": end_year,
        "status": "capturing",
        "sessions": [],
    }

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch_persistent_context(str(profile_dir), headless=False)
        page = browser.pages[0] if browser.pages else await browser.new_page()
        await page.goto("https://ednpro.app/annales", wait_until="domcontentloaded")
        if "/auth" in page.url:
            try:
                await page.wait_for_url(lambda url: "/auth" not in url, timeout=300_000)
            except PlaywrightTimeoutError as exc:
                manifest["status"] = "connexion_requise"
                (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                await browser.close()
                raise RuntimeError("Connexion Google EDNpro non terminée") from exc

        annales = parse_annale_links(await page.content(), page.url)
        await page.goto("https://ednpro.app/videos", wait_until="domcontentloaded")
        video_rows = parse_video_cards(await page.content(), page.url)
        for row in annales:
            year = _year(f"{row['title']} {row['url']}", start_year)
            if year < start_year or (end_year is not None and year > end_year):
                continue
            session_id = _slug(row["url"].rstrip("/").split("/")[-1])
            entry = {"title": row["title"], "url": row["url"], "year": year, "session_id": session_id}
            try:
                await page.goto(row["url"], wait_until="domcontentloaded")
                title = (await page.title()).strip() or row["title"] or session_id
                payload = extract_exam_payload(
                    await page.content(),
                    url=page.url,
                    title=title,
                    year=year,
                    session_id=session_id,
                    resources=video_rows,
                )
                source_path = run_dir / f"{session_id}.source.json"
                source_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                entry.update({"source_json": str(source_path), "questions": len(payload["questions"])})
                if auto_correct:
                    if not payload["questions"]:
                        raise ValueError("Aucune question détectée ; import bloqué pour éviter un faux EDN complet")
                    output_path = import_service.VERIFIED_DIR / f"ednpro-{year}-{session_id}.json"
                    entry["import"] = generate_and_import_ednpro(payload, service=service, output_path=output_path)
                    entry["status"] = "imported"
                else:
                    entry["status"] = "captured"
            except Exception as exc:  # keep later sessions resumable
                entry.update({"status": "retryable_error", "error": str(exc)})
            manifest["sessions"].append(entry)
        await browser.close()

    manifest["status"] = "completed"
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Collecter et importer les EDN EDNpro")
    parser.add_argument("--start-year", type=int, default=2023)
    parser.add_argument("--end-year", type=int)
    parser.add_argument("--no-ai", action="store_true", help="collecte seule, sans correction ni import")
    parser.add_argument("--profile-dir", type=Path, default=Path("data/ednpro/browser-profile"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/ednpro/artifacts"))
    args = parser.parse_args()
    path = asyncio.run(collect_ednpro(
        start_year=args.start_year,
        end_year=args.end_year,
        profile_dir=args.profile_dir,
        output_dir=args.output_dir,
        auto_correct=not args.no_ai,
    ))
    print(path)


if __name__ == "__main__":
    main()
