"""
scripts/reconcile_item_numbers.py
----------------------------------
Corrige les pages Cours Notion dont ITEM (number) est vide alors qu'ITEM lié
(relation) est renseignée et resolvable — cause racine des fiches Obsidian
orphelines (chantier C5, voir docs/superpowers/specs/2026-08-09-chantier-c5-*).

Ne modifie que la propriété ITEM (number) des pages concernées. Rien d'autre.

À exécuter AVANT scripts/heal_obsidian_item_frontmatter.py --apply : ce
script-ci doit avoir été lancé en --apply pour que le second script trouve
des display_item_number déjà corrigés côté Notion.

Usage :
    python scripts/reconcile_item_numbers.py            # dry-run (rapporte le plan)
    python scripts/reconcile_item_numbers.py --apply     # écrit réellement dans Notion
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

from backend.config.settings import NOTION_PROPS as P
from backend.core.notion.models import Cours
from backend.core.notion.service import notion_service

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_PATH = os.path.join(BASE, "data", "item_number_reconcile_report.json")
RESULT_PATH = os.path.join(BASE, "data", "item_number_apply_result.json")

RATE_LIMIT_DELAY = 0.35  # ~3 req/s, marge sous la limite Notion


def find_item_number_corrections(cours: list[Cours], page_id_to_item_num: dict[str, int]) -> list[dict]:
    """Cours avec ITEM (number) vide mais ITEM lié résolvable vers un item connu."""
    corrections: list[dict] = []
    for c in cours:
        has_number = bool((c.item_number or "").strip())
        if has_number or not c.item_lie:
            continue
        resolved = page_id_to_item_num.get(c.item_lie)
        if resolved is not None:
            corrections.append({"page_id": c.id, "title": c.title, "item_number": resolved})
    return corrections


async def main() -> None:
    apply_mode = "--apply" in sys.argv

    logger.info("Récupération des cours et des items Notion…")
    cours = await notion_service.get_all_cours()
    items_map = await notion_service.get_all_items_map()  # item_number(int) -> Item page id
    page_id_to_item_num = {v: k for k, v in items_map.items()}

    corrections = find_item_number_corrections(cours, page_id_to_item_num)
    logger.info(f"{len(corrections)} correction(s) trouvée(s) sur {len(cours)} cours.")

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump({"corrections": corrections}, f, ensure_ascii=False, indent=2)

    if not apply_mode:
        print(f"\n[DRY RUN] {len(corrections)} correction(s) prévue(s).")
        print(f"Détail : {REPORT_PATH}")
        print("Relancer avec --apply pour écrire réellement dans Notion.")
        return

    applied: list[dict] = []
    errors: list[dict] = []
    for i, corr in enumerate(corrections, 1):
        try:
            ok = await notion_service.update_course(
                corr["page_id"], {P.ITEM: {"number": float(corr["item_number"])}},
            )
            if ok:
                applied.append(corr)
            else:
                errors.append({**corr, "error": "update_course a renvoyé False"})
        except Exception as e:
            logger.error(f"Échec correction {corr['title']!r} (item {corr['item_number']}): {e}")
            errors.append({**corr, "error": str(e)})
        if i % 20 == 0 or i == len(corrections):
            logger.info(f"  traité {i}/{len(corrections)}")
        await asyncio.sleep(RATE_LIMIT_DELAY)

    result = {"applied_count": len(applied), "error_count": len(errors), "applied": applied, "errors": errors}
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n=== Terminé ===")
    print(f"  corrigées : {len(applied)}/{len(corrections)}")
    print(f"  erreurs   : {len(errors)}")
    print(f"\nRésultat détaillé : {RESULT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
