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


_ITEM_RE = re.compile(r"^(?:(?:item|num[ée]ro)\s*)?(\d{2,3})\s*[-–=.\s]", re.IGNORECASE)


def _extract_item_number(filename: str) -> int | None:
    m = _ITEM_RE.match(os.path.splitext(filename)[0])
    if m:
        n = int(m.group(1))
        if 1 <= n <= 400:
            return n
    return None


async def auto_import_courses_from_pdf_folders(
    cours_existants: list[Cours],
    force: bool = False,
) -> dict:
    """
    Scanne les dossiers Collèges/{college}/items/*.pdf et crée dans Notion
    les cours dont le numéro d'item n'existe pas encore.

    Paramètres :
        cours_existants : liste des cours déjà chargés depuis Notion.
        force           : si True, efface le cache SQLite et rescanne tout.

    Retourne :
        dict avec les clés 'created', 'existing_skipped', 'failed', 'total_found'.

    Ne bloque jamais le démarrage — appeler via asyncio.create_task().
    """
    result = {"created": 0, "existing_skipped": 0, "failed": 0, "total_found": 0}

    try:
        from backend.core.qcm.items_mapping import all_items, get_college_from_item
        from backend.config.settings import settings, NOTION_PROPS as P
        from backend.core.notion.service import notion_service
        from backend.core.notion.client import notion_client
        from backend.core.reviews import local_store
    except ImportError as exc:
        logger.warning(f"PDF import: imports manquants, fonctionnalité désactivée — {exc}")
        return result

    try:
        return await _run_import(
            cours_existants, force, result,
            settings=settings, P=P,
            notion_service=notion_service,
            notion_client=notion_client,
            local_store=local_store,
            all_items=all_items,
            get_college_from_item=get_college_from_item,
        )
    except Exception as exc:
        logger.error(f"PDF import: erreur inattendue — {exc}")
        return result


async def _run_import(
    cours_existants, force, result, *,
    settings, P, notion_service, notion_client, local_store,
    all_items, get_college_from_item,
) -> dict:
    medicine_dir = getattr(settings, "medicine_dir", None)
    if not medicine_dir or not os.path.isdir(medicine_dir):
        logger.info("PDF import: medicine_dir non configuré ou introuvable — scan ignoré")
        return result

    colleges_root = os.path.join(medicine_dir, "Collèges")
    if not os.path.isdir(colleges_root):
        logger.info(f"PDF import: dossier '{colleges_root}' introuvable — scan ignoré")
        return result

    # ── Items EDN valides ─────────────────────────────────────────────────────
    valid_items: dict[int, dict] = {item["item"]: item for item in all_items()}
    if not valid_items:
        logger.warning("PDF import: items_edn.json vide ou manquant — scan ignoré")
        return result

    # ── Cours déjà présents dans Notion : set de (item_number, college) ───────
    existing: set[tuple[int, str]] = set()
    for c in cours_existants:
        try:
            n = int(float(c.item_number)) if c.item_number else None
        except (ValueError, TypeError):
            n = None
        if n:
            for col in (getattr(c, "college", None) or []):
                existing.add((n, col))

    # ── Cache SQLite : (college, item_num) déjà traités ──────────────────────
    if force:
        deleted = local_store.reset_pdf_scan()
        logger.info(f"PDF import: force rescan — {deleted} entrées cache effacées")
        processed: set[tuple[str, int]] = set()
    else:
        processed = local_store.get_processed_pdf_items()

    # ── Scan des dossiers Collèges/ ───────────────────────────────────────────
    to_create: list[dict] = []

    try:
        folder_names = os.listdir(colleges_root)
    except OSError as exc:
        logger.warning(f"PDF import: impossible de lire {colleges_root} — {exc}")
        return result

    for folder_name in folder_names:
        folder_path = os.path.join(colleges_root, folder_name)
        if not os.path.isdir(folder_path):
            continue

        # Cherche tout sous-dossier dont le nom commence par "item"
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

        # Si plusieurs dossiers item*, prend le plus récemment modifié
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

            # Collège Notion via les données EDN (fiable, pas de collision COLLEGE_MAPPING)
            notion_college = get_college_from_item(item_num)
            if not notion_college:
                logger.debug(f"PDF import: item {item_num} sans collège EDN assigné — {fname!r}")
                continue

            result["total_found"] += 1

            # Skip si déjà traité avec succès (cache SQLite)
            if (notion_college, item_num) in processed:
                continue

            # Skip si déjà dans Notion, mémoriser dans le cache
            if (item_num, notion_college) in existing:
                local_store.upsert_pdf_scan(notion_college, item_num, "existing", fname)
                result["existing_skipped"] += 1
                continue

            to_create.append({
                "item_number": item_num,
                "college": notion_college,
                "title": valid_items[item_num]["title"],
                "source_file": fname,
            })

    if not to_create:
        logger.info(
            f"PDF import: aucun cours manquant "
            f"({result['total_found']} PDFs scannés, {len(processed)} déjà traités)"
        )
        return result

    logger.info(f"PDF import: {len(to_create)} cours à créer dans Notion")

    # ── Items map pour la relation ITEM_LIE ───────────────────────────────────
    try:
        items_map: dict[int, str] = await notion_service.get_all_items_map()
    except Exception as exc:
        logger.warning(f"PDF import: impossible de récupérer items_map — {exc}")
        return result

    cours_db_id = getattr(settings.notion, "cours_db_id", None)
    if not cours_db_id:
        logger.warning("PDF import: cours_db_id non configuré — création impossible")
        return result

    # ── Création Notion ───────────────────────────────────────────────────────
    for entry in to_create:
        num = entry["item_number"]
        college = entry["college"]
        title = entry["title"]
        fname = entry["source_file"]

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
            await notion_client.create_page(parent_db_id=cours_db_id, properties=props)
            logger.success(f"PDF import: ✓ Item {num:>3} ({college}) — {title[:60]}")
            local_store.upsert_pdf_scan(college, num, "created", fname)
            result["created"] += 1
        except Exception as exc:
            logger.error(f"PDF import: ✗ Item {num:>3} — {exc}")
            local_store.upsert_pdf_scan(college, num, "failed", fname)
            result["failed"] += 1

        await asyncio.sleep(0.35)  # Respecte le rate-limit Notion (~3 req/s)

    logger.info(
        f"PDF import terminé — créés : {result['created']} "
        f"| erreurs : {result['failed']} "
        f"| déjà présents : {result['existing_skipped']}"
    )
    return result
