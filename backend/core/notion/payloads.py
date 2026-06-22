"""
Helpers pour construire les payloads Notion en écriture.

Usage :
    from backend.core.notion.payloads import checkbox, number, notion_date, url_prop, relation

    await notion_service.update_course(c.id, {
        NOTION_PROPS.RAPPEL_COLLEGE: checkbox(True),
        NOTION_PROPS.NB_LECTURES_COLLEGE: number(3),
    })
"""
from __future__ import annotations


def checkbox(value: bool) -> dict:
    """Propriété Checkbox Notion."""
    return {"checkbox": bool(value)}


def number(value: int | float) -> dict:
    """Propriété Nombre Notion."""
    return {"number": value}


def notion_date(date_str: str) -> dict:
    """Propriété Date Notion (format ISO 'YYYY-MM-DD')."""
    return {"date": {"start": date_str}}


def url_prop(value: str | None) -> dict:
    """Propriété URL Notion."""
    return {"url": value}


def relation(page_ids: list[str]) -> dict:
    """Propriété Relation Notion."""
    return {"relation": [{"id": pid} for pid in page_ids]}


def select(name: str) -> dict:
    """Propriété Select Notion."""
    return {"select": {"name": name}}


def rich_text(text: str) -> dict:
    """Propriété Rich Text Notion."""
    return {"rich_text": [{"text": {"content": text}}]}
