"""Pure HTML helpers shared by the EDNpro Playwright collector.

The collector stores stable EDNpro page URLs and metadata, never media blobs or
short-lived CDN URLs. Browser orchestration lives in the script layer so these
helpers remain cheap and deterministic to test.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

_ITEM_PATTERN = re.compile(r"\bitem\s*#?\s*(\d{1,3}(?:\.\d+)?)\b", re.IGNORECASE)


def normalize_stable_resource_url(value: str) -> str:
    """Return a stable page URL, dropping fragments and ephemeral query data."""
    raw = str(value or "").strip()
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("URL EDNpro invalide")
    # EDNpro page routes are stable without query parameters. Dropping the whole
    # query is safer than accidentally persisting a future signed/session key.
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _item_numbers(text: str) -> list[str]:
    return list(dict.fromkeys(match.group(1) for match in _ITEM_PATTERN.finditer(text or "")))


def parse_video_cards(html: str, base_url: str) -> list[dict]:
    """Extract visible video cards without following or downloading their media."""
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    seen: set[str] = set()
    for card in soup.select(
        "a.video-card, a[data-video-url], [data-video-card], a[href*='/videos/']"
    ):
        href = card.get("href") or card.get("data-video-url") or card.get("data-href")
        if not href:
            continue
        try:
            url = normalize_stable_resource_url(urljoin(base_url, href))
        except ValueError:
            continue
        if url in seen:
            continue
        seen.add(url)
        title_node = card.select_one("h1, h2, h3, h4, [data-title]")
        title = (title_node.get_text(" ", strip=True) if title_node else card.get_text(" ", strip=True))
        section = card.find_parent(attrs={"data-category": True})
        category = str(section.get("data-category", "")) if section else ""
        rows.append({
            "title": title,
            "category": category,
            "url": url,
            "item_numbers": _item_numbers(title),
        })
    return rows


def parse_annale_links(html: str, base_url: str) -> list[dict]:
    """Extract and deduplicate EDNpro annale/session links."""
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    seen: set[str] = set()
    for link in soup.select("a[href]"):
        href = str(link.get("href") or "")
        if "/annales/" not in href or href.rstrip("/").endswith("/annales"):
            continue
        try:
            url = normalize_stable_resource_url(urljoin(base_url, href))
        except ValueError:
            continue
        if url in seen:
            continue
        seen.add(url)
        rows.append({"title": link.get_text(" ", strip=True), "url": url})
    return rows


def _unique_strings(values: object) -> list[str]:
    if isinstance(values, (list, tuple, set)):
        candidates = values
    else:
        candidates = [values]
    return list(dict.fromkeys(
        str(value).strip() for value in candidates
        if value is not None and str(value).strip()
    ))


def _record_index(records: list[dict], key: str) -> dict[str, dict]:
    return {
        str(record.get(key)): record
        for record in records
        if record.get(key) is not None
    }


def _record_text(record: dict, *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())
    return ""


def build_video_resources_from_records(records: list[dict]) -> list[dict]:
    """Turn EDNpro's item-linked video rows into stable Synapse resources.

    The page is a React view backed by Supabase, so this is intentionally based
    on the row contract rather than on the visual card markup. Rows without a
    stable URL are ignored instead of creating unusable resources.
    """
    resources: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for record in records:
        raw_url = record.get("url") or record.get("video_url") or record.get("href")
        if not raw_url:
            continue
        try:
            url = normalize_stable_resource_url(str(raw_url))
        except ValueError:
            continue
        title = str(record.get("title") or record.get("name") or "Vidéo EDNpro").strip()
        item_values = record.get("item_edn")
        if item_values is None:
            item_values = record.get("item_number")
        if item_values is None:
            item_values = record.get("item_numbers")
        item_numbers = _unique_strings(item_values)
        if not item_numbers:
            item_numbers = _item_numbers(title)
        key = (url, ",".join(item_numbers))
        if key in seen:
            continue
        seen.add(key)
        resources.append({
            "title": title,
            "url": url,
            "type": "video",
            "item_numbers": item_numbers,
        })
    return resources


def build_ednpro_exam_payload(
    *,
    session: dict,
    dossiers: list[dict],
    questions: list[dict],
    propositions: list[dict],
    question_oic: list[dict],
    resources: list[dict] | None = None,
    url: str | None = None,
) -> dict:
    """Join the records returned by the EDNpro annale player.

    EDNpro separates its data into session, dossier, question, proposition and
    OIC/item tables. Keeping this join pure makes it testable without a browser
    and prevents an empty shell from ever reaching the import service.
    """
    session_id = str(session.get("id") or "").strip()
    if not session_id:
        raise ValueError("Session EDNpro sans identifiant")
    if not questions:
        raise ValueError("L'annale EDNpro ne contient aucune question")

    dossier_by_id = _record_index(dossiers, "id")
    propositions_by_question: dict[str, list[dict]] = {}
    for proposition in propositions:
        question_id = str(proposition.get("question_id") or "").strip()
        if question_id:
            propositions_by_question.setdefault(question_id, []).append(proposition)
    for rows in propositions_by_question.values():
        rows.sort(key=lambda row: str(row.get("lettre") or row.get("id") or ""))

    items_by_question: dict[str, list[str]] = {}
    for link in question_oic:
        question_id = str(link.get("question_id") or "").strip()
        item_number = link.get("item_number")
        if question_id and item_number is not None:
            items_by_question.setdefault(question_id, []).append(str(item_number).strip())

    year = session.get("annee", session.get("year"))
    if isinstance(year, str) and year.isdigit():
        year = int(year)
    if not isinstance(year, int) or isinstance(year, bool):
        raise ValueError("Année EDNpro invalide")
    session_label = str(session.get("session_label") or "").strip()
    epreuve = str(session.get("epreuve") or "").strip()
    suffix = " · ".join(value for value in (session_label, epreuve) if value)
    title = f"EDN {year}" + (f" — {suffix}" if suffix else "")
    source_url = url or f"https://ednpro.app/annales/{session_id}?mode=consultation"

    normalized_questions = []
    normalized_dossiers = []
    for dossier in dossiers:
        dossier_id = str(dossier.get("id") or "").strip()
        if not dossier_id:
            continue
        normalized_dossiers.append({
            "id": dossier_id,
            "numero": dossier.get("numero_dossier"),
            "type": str(dossier.get("type_dossier") or "").strip(),
            "title": _record_text(dossier, "title", "nom", "label"),
            "context": _record_text(
                dossier, "enonce", "enonce_patient", "context", "description", "texte", "content"
            ),
            "question_ids": [
                str(row.get("id")) for row in questions
                if str(row.get("dossier_id") or "") == dossier_id and row.get("id") is not None
            ],
        })
    for index, question in enumerate(questions, start=1):
        question_id = str(question.get("id") or f"{session_id}-q-{index}")
        dossier = dossier_by_id.get(str(question.get("dossier_id") or ""), {})
        dossier_context = _record_text(
            dossier, "enonce", "enonce_patient", "context", "description", "texte", "content"
        )
        choices = []
        for choice_index, proposition in enumerate(propositions_by_question.get(question_id, []), start=1):
            choice_id = str(proposition.get("id") or f"{question_id}-p-{choice_index}")
            raw_correct = proposition.get("is_correct")
            correct = raw_correct if isinstance(raw_correct, bool) else (
                bool(raw_correct) if raw_correct in (0, 1) else None
            )
            choices.append({
                "id": choice_id,
                "text": str(proposition.get("texte") or proposition.get("text") or "").strip(),
                "correct": correct,
                "source_explanation": _record_text(
                    proposition, "explanation", "ai_explanation"
                ),
            })
        item_numbers = list(dict.fromkeys(
            item for item in items_by_question.get(question_id, []) if item
        ))
        normalized_questions.append({
            "id": question_id,
            "type": str(question.get("type") or ""),
            "stem": str(question.get("enonce") or question.get("stem") or "").strip(),
            "source_explanation": _record_text(question, "explanation", "ai_explanation"),
            "choices": choices,
            "item_numbers": item_numbers,
            "dp_context": {
                "dossier_id": str(question.get("dossier_id") or ""),
                "dossier_number": dossier.get("numero_dossier"),
                "dossier_type": dossier.get("type_dossier", ""),
                "dossier_context": dossier_context,
            },
        })

    return {
        "title": title,
        "year": year,
        "session_id": session_id,
        "exam_id": session_id,
        "url": source_url,
        "subject": str(session.get("subject") or session.get("matiere") or "").strip(),
        "dossiers": normalized_dossiers,
        "questions": normalized_questions,
        "resources": resources or [],
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "collection_status": "captured",
    }
