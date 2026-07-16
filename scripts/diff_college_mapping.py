"""
scripts/diff_college_mapping.py
----------------------------------
Calcule le mapping cible item -> colleges Notion (a partir du referentiel
officiel UNESS/nexternat + de la consolidation validee), le compare a l'etat
reel de la base Notion Cours, et exporte le diff. Lecture seule, n'ecrit rien.

Usage :
    python scripts/diff_college_mapping.py
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

from backend.core.notion.service import notion_service

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEXTERNAT_PATH = os.path.join(BASE, "data", "nexternat_items.json")
CONSOLIDATION_PATH = os.path.join(BASE, "data", "college_consolidation.json")
OUT_PATH = os.path.join(BASE, "data", "college_diff_report.json")


def build_target_mapping() -> dict[int, set[str]]:
    nexternat = json.load(open(NEXTERNAT_PATH, encoding="utf-8"))
    consolidation = json.load(open(CONSOLIDATION_PATH, encoding="utf-8"))
    mapping: dict[str, str | None] = consolidation["mapping"]

    target: dict[int, set[str]] = {}
    for item_num_str, it in nexternat["items"].items():
        item_num = int(item_num_str)
        colleges: set[str] = set()
        for c in it["ecriture"] + it["relecture"]:
            notion_college = mapping.get(c["acronym"])
            if notion_college:
                colleges.add(notion_college)
        target[item_num] = colleges
    return target


async def main() -> None:
    target = build_target_mapping()
    unclassified = sorted(n for n, cols in target.items() if not cols)
    logger.info(f"{len(target)} items cibles construits — {len(unclassified)} sans college (attendu : items Humanites)")

    logger.info("Récupération des cours Notion…")
    cours_existants = await notion_service.get_all_cours()
    items_map = await notion_service.get_all_items_map()
    page_id_to_item_num = {v: k for k, v in items_map.items()}

    # item -> (page_id, current_colleges) ; un item peut avoir plusieurs pages Cours
    # (multi-college split) donc on agrege les colleges actuels par item, et on garde
    # la liste des pages a mettre a jour.
    current_by_item: dict[int, set[str]] = {}
    pages_by_item: dict[int, list[str]] = {}
    for c in cours_existants:
        n: int | None = None
        try:
            n = int(float(c.item_number)) if c.item_number else None
        except (ValueError, TypeError):
            n = None
        if n is None and c.item_lie:
            n = page_id_to_item_num.get(c.item_lie)
        if n is None:
            continue
        current_by_item.setdefault(n, set()).update(c.college or [])
        pages_by_item.setdefault(n, []).append(c.id)

    diffs = []
    items_missing_from_notion = []
    for item_num, target_colleges in sorted(target.items()):
        if not target_colleges:
            continue  # items volontairement sans college (Humanites)
        if item_num not in current_by_item:
            items_missing_from_notion.append(item_num)
            continue
        current_colleges = current_by_item[item_num]
        to_add = sorted(target_colleges - current_colleges)
        to_remove = sorted(current_colleges - target_colleges)
        if to_add or to_remove:
            diffs.append({
                "item": item_num,
                "current": sorted(current_colleges),
                "target": sorted(target_colleges),
                "to_add": to_add,
                "to_remove": to_remove,
                "page_ids": pages_by_item[item_num],
            })

    items_with_additions = [d for d in diffs if d["to_add"]]
    items_with_removals = [d for d in diffs if d["to_remove"]]

    report = {
        "total_target_items": len(target),
        "unclassified_by_design": unclassified,
        "items_missing_from_notion": items_missing_from_notion,
        "items_with_diff": len(diffs),
        "items_with_additions": len(items_with_additions),
        "items_with_removals": len(items_with_removals),
        "diffs": diffs,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n=== Résumé ===")
    print(f"  items cibles (avec college)         : {len(target) - len(unclassified)}")
    print(f"  items sans college (design, Humanités): {len(unclassified)} -> {unclassified}")
    print(f"  items absents de Notion              : {len(items_missing_from_notion)} -> {items_missing_from_notion}")
    print(f"  items avec un ecart                  : {len(diffs)}")
    print(f"    dont avec collège(s) à AJOUTER      : {len(items_with_additions)}")
    print(f"    dont avec collège(s) EN TROP        : {len(items_with_removals)}")
    print(f"\nRapport : {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
