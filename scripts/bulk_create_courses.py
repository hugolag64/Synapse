"""
scripts/bulk_create_courses.py
-------------------------------
Crée en masse les cours Notion pour un collège EDN.

Usage :
    python scripts/bulk_create_courses.py Psy
    python scripts/bulk_create_courses.py MCV

Le script est idempotent : les items déjà présents (même numéro ITEM) sont ignorés.
"""
from __future__ import annotations

import asyncio
import sys
import os

# Assure que le projet est dans le path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from backend.core.notion.client import notion_client
from backend.core.notion.service import notion_service
from backend.core.qcm.items_mapping import all_items, college_full, item_college_abbr
from backend.config.settings import settings, NOTION_PROPS as P


async def bulk_create(college_abbr: str) -> None:
    college_notion = college_full(college_abbr)
    if not college_notion:
        logger.error(f"Abréviation inconnue : {college_abbr!r}")
        return

    # Items EDN du collège ciblé
    targets = [
        item for item in all_items()
        if item["college"] == college_abbr
    ]
    if not targets:
        logger.error(f"Aucun item trouvé pour l'abréviation {college_abbr!r}")
        return

    logger.info(f"Collège : {college_notion} — {len(targets)} items EDN à traiter")

    # Paires (item_number, college_notion) déjà présentes dans Notion
    logger.info("Récupération des cours existants…")
    existing_pairs: set[tuple[int, str]] = set()
    existing_courses = await notion_service.get_all_cours()
    for c in existing_courses:
        try:
            n = int(float(c.item_number)) if c.item_number else None
            if n:
                for col in c.college:
                    existing_pairs.add((n, col))
        except (ValueError, TypeError):
            pass
    logger.info(f"{len(existing_courses)} cours existants dans Notion")

    # Map item_number → page_id de la DB Items (pour ITEM lié)
    logger.info("Récupération de la DB Items…")
    items_map: dict[int, str] = await notion_service.get_all_items_map()
    logger.info(f"{len(items_map)} items dans la DB Items")

    to_create = [
        item for item in targets
        if (item["item"], college_notion) not in existing_pairs
    ]
    skipped   = len(targets) - len(to_create)

    logger.info(f"À créer : {len(to_create)} | Déjà existants (ignorés) : {skipped}")

    if not to_create:
        logger.success("Rien à faire — tous les cours existent déjà.")
        return

    created = 0
    errors  = 0

    for item in to_create:
        num   = item["item"]
        title = item["title"]

        properties = {
            P.COURS_TITLE: {"title": [{"text": {"content": title}}]},
            P.COLLEGE:     {"multi_select": [{"name": college_notion}]},
            P.ITEM:        {"number": num},
        }

        # Lier ITEM lié si la page Item existe dans la DB
        if num in items_map:
            properties[P.ITEM_LIE] = {"relation": [{"id": items_map[num]}]}
        else:
            logger.warning(f"Item {num} absent de la DB Items — ITEM lié non renseigné")

        try:
            await notion_client.create_page(
                parent_db_id=settings.notion.cours_db_id,
                properties=properties,
            )
            logger.success(f"  ✓ ITEM {num:>3} — {title[:60]}")
            created += 1
        except Exception as e:
            logger.error(f"  ✗ ITEM {num:>3} — {e}")
            errors += 1

        # Petite pause pour éviter le rate-limit Notion (3 req/s)
        await asyncio.sleep(0.35)

    logger.info(f"\nTerminé — créés : {created} | erreurs : {errors} | ignorés : {skipped}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage : python scripts/bulk_create_courses.py <ABBR>")
        print("Exemple : python scripts/bulk_create_courses.py Psy")
        sys.exit(1)

    asyncio.run(bulk_create(sys.argv[1]))
