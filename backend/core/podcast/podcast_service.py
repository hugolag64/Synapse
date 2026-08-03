"""
podcast_service.py — Service de gestion et parsing du Podcast « L'EXTERNE ».
-----------------------------------------------------------------------------
Flux RSS : https://anchor.fm/s/db4f429c/podcast/rss
Extrait automatiquement le numéro d'item canonique à partir du titre des épisodes :
Ex: "Episode 122 - Addiction au tabac (item 75)" -> Item 75
"""

from __future__ import annotations

import datetime
import re
import xml.etree.ElementTree as ET
import urllib.request
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


PODCAST_RSS_URL = "https://anchor.fm/s/db4f429c/podcast/rss"
_ITEM_REGEX = re.compile(r"\(item\s*(\d+)\)", re.IGNORECASE)


@dataclass
class PodcastEpisode:
    title: str
    item_number: str
    audio_url: str
    pub_date: str
    duration: str
    link: str


_cache: dict[str, list[PodcastEpisode]] = {}
_last_fetch: Optional[datetime.datetime] = None
_FETCH_INTERVAL_MINUTES = 60


def fetch_podcast_episodes(force_refresh: bool = False) -> dict[str, list[PodcastEpisode]]:
    """
    Récupère et parse le flux RSS du podcast L'EXTERNE.
    Indexe les épisodes par numéro d'item canonique (ex: "75").
    """
    global _last_fetch, _cache
    now = datetime.datetime.now()

    if not force_refresh and _cache and _last_fetch and (now - _last_fetch).total_seconds() < _FETCH_INTERVAL_MINUTES * 60:
        return _cache

    try:
        req = urllib.request.Request(
            PODCAST_RSS_URL,
            headers={"User-Agent": "Synapse-EDN-App/2026"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            xml_data = resp.read()

        root = ET.fromstring(xml_data)
        channel = root.find("channel")
        if channel is None:
            return _cache

        new_index: dict[str, list[PodcastEpisode]] = {}

        for item in channel.findall("item"):
            raw_title = item.findtext("title") or ""
            match = _ITEM_REGEX.search(raw_title)
            if not match:
                continue

            item_num = match.group(1).strip()
            
            enclosure = item.find("enclosure")
            audio_url = enclosure.get("url") if enclosure is not None else ""
            if not audio_url:
                continue

            pub_date = item.findtext("pubDate") or ""
            link = item.findtext("link") or ""

            duration = ""
            for child in item:
                if child.tag.endswith("duration"):
                    duration = child.text or ""
                    break

            episode = PodcastEpisode(
                title=raw_title,
                item_number=item_num,
                audio_url=audio_url,
                pub_date=pub_date[:16] if pub_date else "",
                duration=duration,
                link=link,
            )

            new_index.setdefault(item_num, []).append(episode)

        _cache = new_index
        _last_fetch = now
        logger.info(f"Podcast L'EXTERNE : {sum(len(v) for v in new_index.values())} épisodes indexés pour {len(new_index)} items.")
        return _cache

    except Exception as exc:
        logger.warning(f"Erreur lors de la récupération du podcast L'EXTERNE : {exc}")
        return _cache


def get_episodes_for_item(item_number: str | None) -> list[PodcastEpisode]:
    """Retourne la liste des épisodes associés à un numéro d'item canonique."""
    if not item_number:
        return []
    clean_num = str(item_number).strip().lstrip("0")
    episodes = fetch_podcast_episodes().get(clean_num, [])
    return list(reversed(episodes))
