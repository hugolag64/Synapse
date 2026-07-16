"""
scripts/apply_college_corrections.py
---------------------------------------
Applique dans Notion le resultat du diff calcule par diff_college_mapping.py :

  - Pattern reel observe dans la base Cours : UNE page = UN (item, college).
    Donc "ajouter un college" = creer une nouvelle page Cours pour ce couple,
    et "retirer un college" = archiver la ou les pages existantes pour ce couple.
  - Les 3 nouvelles categories College (Biologie Cellulaire, Biochimie et
    Biologie Moleculaire, Medecine du travail) sont creees implicitement par
    Notion des la premiere page qui les utilise (multi_select auto-create).
  - Les items totalement absents de Notion recoivent une nouvelle page Cours
    par college cible, avec le numero ITEM correctement renseigne (+ relation
    ITEM lie quand la page Item correspondante est connue).

Usage :
    python scripts/apply_college_corrections.py            # dry-run (rapporte le plan)
    python scripts/apply_college_corrections.py --apply     # ecrit reellement dans Notion
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from loguru import logger

from backend.config.settings import settings, NOTION_PROPS as P
from backend.core.notion.client import notion_client
from backend.core.notion.service import notion_service

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIFF_PATH = os.path.join(BASE, "data", "college_diff_report.json")
NEXTERNAT_PATH = os.path.join(BASE, "data", "nexternat_items.json")
CONSOLIDATION_PATH = os.path.join(BASE, "data", "college_consolidation.json")
RESULT_PATH = os.path.join(BASE, "data", "college_apply_result.json")

RATE_LIMIT_DELAY = 0.35  # ~3 req/s, marge sous la limite Notion


def target_colleges_for(item_num: int, nexternat: dict, mapping: dict) -> set[str]:
    it = nexternat["items"][str(item_num)]
    cols: set[str] = set()
    for c in it["ecriture"] + it["relecture"]:
        m = mapping.get(c["acronym"])
        if m:
            cols.add(m)
    return cols


async def create_cours_page(title: str, item_num: int, college: str, item_page_id: str | None) -> str:
    properties: dict = {
        P.COURS_TITLE: {"title": [{"text": {"content": title}}]},
        P.COLLEGE: {"multi_select": [{"name": college}]},
        P.ITEM: {"number": float(item_num)},
    }
    if item_page_id:
        properties[P.ITEM_LIE] = {"relation": [{"id": item_page_id}]}
    response = await notion_client.create_page(parent_db_id=settings.notion.cours_db_id, properties=properties)
    return response["id"]


async def main() -> None:
    apply_mode = "--apply" in sys.argv

    diff_report = json.load(open(DIFF_PATH, encoding="utf-8"))
    nexternat = json.load(open(NEXTERNAT_PATH, encoding="utf-8"))
    consolidation = json.load(open(CONSOLIDATION_PATH, encoding="utf-8"))
    mapping = consolidation["mapping"]

    logger.info("Récupération de l'état actuel des pages Cours (pour cibler les retraits)…")
    cours_existants = await notion_service.get_all_cours()
    items_map = await notion_service.get_all_items_map()  # item_number(int) -> Item page id
    page_id_to_item_num = {v: k for k, v in items_map.items()}

    # (item, college) -> [page_id, ...]  (granularité réelle : 1 page = 1 college)
    pages_by_pair: dict[tuple[int, str], list[str]] = {}
    for c in cours_existants:
        try:
            n = int(float(c.item_number)) if c.item_number else None
        except (ValueError, TypeError):
            n = None
        if n is None and c.item_lie:
            n = page_id_to_item_num.get(c.item_lie)
        if n is None:
            continue
        for col in (c.college or []):
            pages_by_pair.setdefault((n, col), []).append(c.id)

    # ── Construction du plan ────────────────────────────────────────────────
    creates: list[dict] = []   # {item, college, title}
    archives: list[dict] = []  # {item, college, page_id}

    for d in diff_report["diffs"]:
        item_num = d["item"]
        title = nexternat["items"][str(item_num)]["title"]
        for college in d["to_add"]:
            creates.append({"item": item_num, "college": college, "title": title})
        for college in d["to_remove"]:
            for pid in pages_by_pair.get((item_num, college), []):
                archives.append({"item": item_num, "college": college, "page_id": pid})

    for item_num in diff_report["items_missing_from_notion"]:
        title = nexternat["items"][str(item_num)]["title"]
        for college in sorted(target_colleges_for(item_num, nexternat, mapping)):
            creates.append({"item": item_num, "college": college, "title": title})

    logger.info(f"Plan : {len(creates)} pages à créer, {len(archives)} pages à archiver")

    if not apply_mode:
        print(f"\n[DRY RUN] {len(creates)} créations, {len(archives)} archivages prévus.")
        print("Relancer avec --apply pour écrire réellement dans Notion.")
        with open(RESULT_PATH, "w", encoding="utf-8") as f:
            json.dump({"mode": "dry_run", "creates": creates, "archives": archives}, f, ensure_ascii=False, indent=2)
        return

    created_ids: list[dict] = []
    archived_ids: list[dict] = []
    errors: list[dict] = []

    for i, op in enumerate(creates, 1):
        item_page_id = items_map.get(op["item"])
        try:
            pid = await create_cours_page(op["title"], op["item"], op["college"], item_page_id)
            created_ids.append({**op, "page_id": pid})
            if i % 20 == 0 or i == len(creates):
                logger.info(f"  créé {i}/{len(creates)}")
        except Exception as e:
            logger.error(f"Échec création item {op['item']} / {op['college']}: {e}")
            errors.append({"op": "create", **op, "error": str(e)})
        await asyncio.sleep(RATE_LIMIT_DELAY)

    for i, op in enumerate(archives, 1):
        try:
            await notion_client.archive_page(op["page_id"])
            archived_ids.append(op)
            if i % 20 == 0 or i == len(archives):
                logger.info(f"  archivé {i}/{len(archives)}")
        except Exception as e:
            logger.error(f"Échec archivage item {op['item']} / {op['college']} ({op['page_id']}): {e}")
            errors.append({"op": "archive", **op, "error": str(e)})
        await asyncio.sleep(RATE_LIMIT_DELAY)

    result = {
        "mode": "applied",
        "created_count": len(created_ids),
        "archived_count": len(archived_ids),
        "error_count": len(errors),
        "created": created_ids,
        "archived": archived_ids,
        "errors": errors,
    }
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n=== Terminé ===")
    print(f"  créées   : {len(created_ids)}/{len(creates)}")
    print(f"  archivées: {len(archived_ids)}/{len(archives)}")
    print(f"  erreurs  : {len(errors)}")
    print(f"\nRésultat détaillé : {RESULT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
