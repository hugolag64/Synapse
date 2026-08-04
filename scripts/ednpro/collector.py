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
from backend.core.ednpro.auth import wait_for_ednpro_auth
from backend.core.ednpro.collector import (
    _item_numbers,
    build_ednpro_exam_payload,
    build_video_resources_from_records,
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


_EDNPRO_TABLES = {
    "annales_sessions",
    "annales_dossiers",
    "annales_questions",
    "annales_propositions",
    "annales_propositions_safe",
    "annales_question_oic",
    "learning_videos",
    "pedagogy_videos",
    "video_item_subjects",
}


def _table_from_response_url(url: str) -> str:
    return str(url).split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]


def _deduplicate_records(records: list[dict]) -> list[dict]:
    result = []
    seen = set()
    for record in records:
        key = str(record.get("id") or json.dumps(record, sort_keys=True, ensure_ascii=False))
        if key in seen:
            continue
        seen.add(key)
        result.append(record)
    return result


async def capture_ednpro_table_records(page: Any, url: str, *, wait_ms: int = 2500) -> dict[str, list[dict]]:
    """Capture the authenticated Supabase rows used by an EDNpro page.

    EDNpro is a client-rendered SPA. The visible page is only a projection of
    these responses; listening to the responses keeps the collector independent
    from CSS classes and from the UNESS navigation model.
    """
    captured: dict[str, list[dict]] = {table: [] for table in _EDNPRO_TABLES}
    tasks: list[asyncio.Task] = []

    async def consume(response: Any, table: str) -> None:
        try:
            data = await response.json()
        except Exception:
            return
        rows = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
        captured[table].extend(row for row in rows if isinstance(row, dict))

    def on_response(response: Any) -> None:
        table = _table_from_response_url(response.url)
        if table in _EDNPRO_TABLES:
            tasks.append(asyncio.create_task(consume(response, table)))

    page.on("response", on_response)
    try:
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(wait_ms)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        page.remove_listener("response", on_response)
    return {table: _deduplicate_records(rows) for table, rows in captured.items()}


def _session_title(session: dict, year: int, session_id: str) -> str:
    label = str(session.get("session_label") or "").strip()
    epreuve = str(session.get("epreuve") or "").strip()
    suffix = " · ".join(value for value in (label, epreuve) if value)
    return f"EDN {year}" + (f" — {suffix}" if suffix else f" — {session_id}")


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
                page = await wait_for_ednpro_auth(page, browser)
            except (PlaywrightTimeoutError, TimeoutError) as exc:
                manifest["status"] = "connexion_requise"
                (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                await browser.close()
                raise RuntimeError("Connexion Google EDNpro non terminée") from exc

        catalog = await capture_ednpro_table_records(page, "https://ednpro.app/annales")
        sessions = [
            row for row in catalog["annales_sessions"]
            if str(row.get("status") or "published") == "published"
            and str(row.get("category") or "annale") in {"annale", "ecni_annale"}
        ]
        if not sessions:
            raise RuntimeError(
                "Aucune session EDNpro reçue. Vérifier la connexion Google et le chargement de /annales."
            )

        videos_page = await capture_ednpro_table_records(page, "https://ednpro.app/videos")
        video_records = videos_page["learning_videos"]
        video_rows = build_video_resources_from_records(video_records)
        if not video_rows:
            # Keep a cheap DOM fallback for older accounts/builds whose video
            # table is not exposed on the page, without making it the primary
            # EDNpro collection strategy.
            video_rows = parse_video_cards(await page.content(), page.url)

        for session in sessions:
            raw_year = session.get("annee", session.get("year"))
            year = int(raw_year) if str(raw_year).isdigit() else _year(str(session), start_year)
            if year < start_year or (end_year is not None and year > end_year):
                continue
            session_id = str(session.get("id") or "").strip()
            if not session_id:
                continue
            session_url = f"https://ednpro.app/annales/{session_id}?mode=consultation"
            entry = {
                "title": _session_title(session, year, session_id),
                "url": session_url,
                "year": year,
                "session_id": session_id,
            }
            try:
                session_data = await capture_ednpro_table_records(page, session_url)
                session_row = next(
                    (row for row in session_data["annales_sessions"] if str(row.get("id")) == session_id),
                    session,
                )
                dossiers = [
                    row for row in session_data["annales_dossiers"]
                    if str(row.get("session_id")) == session_id
                ]
                dossier_ids = {str(row.get("id")) for row in dossiers}
                questions = [
                    row for row in session_data["annales_questions"]
                    if str(row.get("dossier_id")) in dossier_ids
                ]
                question_ids = {str(row.get("id")) for row in questions}
                propositions = [
                    row for row in (session_data["annales_propositions"] or session_data["annales_propositions_safe"])
                    if str(row.get("question_id")) in question_ids
                ]
                question_oic = [
                    row for row in session_data["annales_question_oic"]
                    if str(row.get("question_id")) in question_ids
                ]
                payload = build_ednpro_exam_payload(
                    session=session_row,
                    dossiers=dossiers,
                    questions=questions,
                    propositions=propositions,
                    question_oic=question_oic,
                    resources=video_rows,
                    url=session_url,
                )
                source_path = run_dir / f"{session_id}.source.json"
                source_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                entry.update({"source_json": str(source_path), "questions": len(payload["questions"])})
                if auto_correct:
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
