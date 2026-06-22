"""
Scan des sous-dossiers 'items'/'item' dans les dossiers de collèges,
et création automatique dans Notion des cours absents.

Format attendu des fichiers PDF :
  "Item 325 - Insuffisance cardiaque.pdf"
  "325 - Insuffisance cardiaque.pdf"
"""
from __future__ import annotations

import asyncio
import os
import re
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from backend.core.notion.models import Cours


_ITEM_RE = re.compile(r"^(?:item\s*)?(\d{2,3})\s*[-–]", re.IGNORECASE)


def _extract_item_number(filename: str) -> int | None:
    m = _ITEM_RE.match(os.path.splitext(filename)[0])
    if m:
        n = int(m.group(1))
        if 1 <= n <= 400:
            return n
    return None


async def auto_import_courses_from_pdf_folders(cours_existants: list[Cours]) -> None:
    """
    Tâche background : scan les dossiers Collèges/{college}/items/*.pdf
    et crée dans Notion les cours dont le numéro d'item n'existe pas encore.

    Ne bloque jamais le démarrage — appeler via asyncio.create_task().
    """
    try:
        from backend.core.obsidian.service import COLLEGE_MAPPING
        from backend.core.qcm.items_mapping import all_items
        from backend.config.settings import settings, NOTION_PROPS as P
        from backend.core.notion.service import notion_service
        from backend.core.notion.client import notion_client
    except ImportError as exc:
        logger.warning(f"PDF import: imports manquants, fonctionnalité désactivée — {exc}")
        return

    medicine_dir = getattr(settings, "medicine_dir", None)
    if not medicine_dir or not os.path.isdir(medicine_dir):
        return

    colleges_root = os.path.join(medicine_dir, "Collèges")
    if not os.path.isdir(colleges_root):
        return

    # Disk folder → Notion college name (avec emoji)
    disk_to_college: dict[str, str] = {v: k for k, v in COLLEGE_MAPPING.items()}

    # Items EDN valides : item_number → {item, title, college_abbr, ...}
    valid_items: dict[int, dict] = {item["item"]: item for item in all_items()}

    # Cours déjà présents dans Notion : set of (item_number, college_notion)
    existing: set[tuple[int, str]] = set()
    for c in cours_existants:
        try:
            n = int(float(c.item_number)) if c.item_number else None
        except (ValueError, TypeError):
            n = None
        if n:
            for col in (getattr(c, "college", None) or []):
                existing.add((n, col))

    # ── Scan ──────────────────────────────────────────────────────────────────
    to_create: list[dict] = []

    try:
        folder_names = os.listdir(colleges_root)
    except OSError as exc:
        logger.warning(f"PDF import: impossible de lire {colleges_root} — {exc}")
        return

    for folder_name in folder_names:
        folder_path = os.path.join(colleges_root, folder_name)
        if not os.path.isdir(folder_path):
            continue

        notion_college = disk_to_college.get(folder_name)
        if not notion_college:
            logger.debug(f"PDF import: dossier inconnu dans COLLEGE_MAPPING — {folder_name!r}")
            continue

        # Cherche tout sous-dossier dont le nom commence par "item" (insensible à la casse)
        # Ex : "item", "items", "item 25-26-27", "items 2024"
        # Si plusieurs correspondent, on prend le plus récemment modifié
        try:
            all_subdirs = os.listdir(folder_path)
        except OSError:
            continue
        item_subdirs = [
            os.path.join(folder_path, d)
            for d in all_subdirs
            if d.lower().startswith("item") and os.path.isdir(os.path.join(folder_path, d))
        ]

        if not item_subdirs:
            continue

        # Si plusieurs dossiers item*, on prend le plus récemment modifié
        items_subdir = max(item_subdirs, key=os.path.getmtime)
        if len(item_subdirs) > 1:
            logger.debug(
                f"PDF import: {len(item_subdirs)} dossiers item* dans {folder_name!r} "
                f"→ sélectionné : {os.path.basename(items_subdir)!r}"
            )

        try:
            pdf_files = [f for f in os.listdir(items_subdir) if f.lower().endswith(".pdf")]
        except OSError:
            continue

        for fname in pdf_files:
            item_num = _extract_item_number(fname)
            if item_num is None:
                continue
            if item_num not in valid_items:
                logger.debug(f"PDF import: numéro item {item_num} hors EDN — {fname!r}")
                continue
            if (item_num, notion_college) in existing:
                continue

            to_create.append({
                "item_number": item_num,
                "college": notion_college,
                "title": valid_items[item_num]["title"],
                "source_file": fname,
            })

    if not to_create:
        logger.info("PDF import: aucun cours manquant dans les dossiers items/")
        return

    logger.info(f"PDF import: {len(to_create)} cours à créer dans Notion")

    # ── Création Notion ────────────────────────────────────────────────────────
    try:
        items_map: dict[int, str] = await notion_service.get_all_items_map()
    except Exception as exc:
        logger.warning(f"PDF import: impossible de récupérer items_map — {exc}")
        return

    cours_db_id = getattr(settings.notion, "cours_db_id", None)
    if not cours_db_id:
        logger.warning("PDF import: cours_db_id non configuré — création impossible")
        return

    created = 0
    errors = 0

    for entry in to_create:
        num = entry["item_number"]
        college = entry["college"]
        title = entry["title"]

        props = {
            P.COURS_TITLE: {"title": [{"text": {"content": title}}]},
            P.COLLEGE: {"multi_select": [{"name": college}]},
            P.ITEM: {"number": num},
        }
        if num in items_map:
            props[P.ITEM_LIE] = {"relation": [{"id": items_map[num]}]}
        else:
            logger.warning(f"PDF import: Item {num} absent de la DB Items — ITEM lié ignoré")

        try:
            await notion_client.create_page(
                parent_db_id=cours_db_id,
                properties=props,
            )
            logger.success(f"PDF import: ✓ Item {num:>3} ({college}) — {title[:60]}")
            created += 1
        except Exception as exc:
            logger.error(f"PDF import: ✗ Item {num:>3} — {exc}")
            errors += 1

        await asyncio.sleep(0.35)  # Respecte le rate-limit Notion (~3 req/s)

    logger.info(f"PDF import terminé — créés : {created} | erreurs : {errors}")
