"""Pure HTML helpers shared by the EDNpro Playwright collector.

The collector stores stable EDNpro page URLs and metadata, never media blobs or
short-lived CDN URLs. Browser orchestration lives in the script layer so these
helpers remain cheap and deterministic to test.
"""

from __future__ import annotations

import re
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
