"""
scripts/set_college_semestre.py
--------------------------------
Corrige la propriete "Semestre" des pages Cours pour les colleges valides,
en se basant sur le semestre reel du programme (donne par l'utilisateur),
et non sur la date d'ajout du college dans l'app.

Pattern observe : 1 page Cours = 1 couple (item, college) -> on peut donc
filtrer par nom de college dans le multi-select et ecrire directement.

Usage :
    python scripts/set_college_semestre.py            # dry-run (rapporte le plan)
    python scripts/set_college_semestre.py --apply     # ecrit reellement dans Notion
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
from backend.core.notion.client import notion_client
from backend.core.notion.service import notion_service

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULT_PATH = os.path.join(BASE, "data", "college_semestre_result.json")

RATE_LIMIT_DELAY = 0.35

# college (nom exact avec emoji, tel que stocke dans Notion) -> semestre cible
TARGET_SEMESTRE: dict[str, str] = {
    "Pneumologie 🫁": "Semestre 3",
    "Néphrologie 🧑‍🔬": "Semestre 4",
    "Cardiovasculaire ❤️": "Semestre 4",
    "Dermatologie 🧴": "Semestre 5",
    "Hépato-Gastro-entérologie 🧻": "Semestre 6",
    "Endocrinologie - Diabétologie - Maladies métaboliques 🫘": "Semestre 6",
    "Nutrition 🍔": "Semestre 6",
    "Neurologie 🧠": "Semestre 6",
    "Neurochirurgie 🧠": "Semestre 6",
    "Infectiologie 🦠": "Semestre 6",
}


async def main() -> None:
    apply_mode = "--apply" in sys.argv

    cours = await notion_service.get_all_cours()

    plan: list[dict] = []
    for c in cours:
        matched = [col for col in (c.college or []) if col in TARGET_SEMESTRE]
        if not matched:
            continue
        if len(matched) > 1:
            targets = {TARGET_SEMESTRE[m] for m in matched}
            if len(targets) > 1:
                logger.warning(
                    f"Page {c.id} ({c.title!r}) a plusieurs colleges cibles avec des "
                    f"semestres differents {matched} -> ignoree, a traiter manuellement."
                )
                continue
        target = TARGET_SEMESTRE[matched[0]]
        if c.semestre == target:
            continue
        plan.append({
            "page_id": c.id,
            "title": c.title,
            "college": matched,
            "old_semestre": c.semestre,
            "new_semestre": target,
        })

    by_college: dict[str, int] = {}
    for op in plan:
        for col in op["college"]:
            by_college[col] = by_college.get(col, 0) + 1

    logger.info(f"Plan : {len(plan)} pages a mettre a jour.")
    for col, n in sorted(by_college.items()):
        logger.info(f"  {col} : {n} page(s)")

    if not apply_mode:
        print(f"\n[DRY RUN] {len(plan)} mises a jour prevues.")
        print("Relancer avec --apply pour ecrire reellement dans Notion.")
        with open(RESULT_PATH, "w", encoding="utf-8") as f:
            json.dump({"mode": "dry_run", "plan": plan}, f, ensure_ascii=False, indent=2)
        return

    updated: list[dict] = []
    errors: list[dict] = []

    for i, op in enumerate(plan, 1):
        try:
            await notion_client.update_page(
                op["page_id"],
                {P.SEMESTRE: {"select": {"name": op["new_semestre"]}}},
            )
            updated.append(op)
            if i % 20 == 0 or i == len(plan):
                logger.info(f"  maj {i}/{len(plan)}")
        except Exception as e:
            logger.error(f"Echec maj {op['title']!r} ({op['page_id']}): {e}")
            errors.append({**op, "error": str(e)})
        await asyncio.sleep(RATE_LIMIT_DELAY)

    result = {
        "mode": "applied",
        "updated_count": len(updated),
        "error_count": len(errors),
        "updated": updated,
        "errors": errors,
    }
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n=== Termine ===")
    print(f"  mises a jour : {len(updated)}/{len(plan)}")
    print(f"  erreurs      : {len(errors)}")
    print(f"\nResultat detaille : {RESULT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
