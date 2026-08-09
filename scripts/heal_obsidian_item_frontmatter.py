"""
scripts/heal_obsidian_item_frontmatter.py
-------------------------------------------
Répare le champ `item:` du frontmatter des fiches Obsidian déjà créées à
partir d'un cours dont ITEM (number) était vide (chantier C5).

À exécuter APRÈS scripts/reconcile_item_numbers.py --apply : ce script lit
Cours.display_item_number, qui ne sera correct que si la correction Notion a
déjà été appliquée.

Ne touche jamais le corps de la note ni aucun autre champ du frontmatter —
seule la ligne `item:` est réécrite, via les mêmes helpers que la création
de note (_rebuild_fm avec un override sur une seule clé).

Usage :
    python scripts/heal_obsidian_item_frontmatter.py            # dry-run
    python scripts/heal_obsidian_item_frontmatter.py --apply    # écrit réellement dans le vault
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from loguru import logger

from backend.config.settings import settings
from backend.core.notion.models import Cours
from backend.core.notion.service import notion_service
from backend.core.obsidian.templates import _parse_fm_lines, _rebuild_fm, _split_frontmatter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_PATH = os.path.join(BASE, "data", "obsidian_item_heal_report.json")


def find_frontmatter_heal_candidates(md_paths: list[Path], course_map: dict[str, Cours]) -> list[dict]:
    """Notes déjà liées (notion_id connu) avec item: vide et un cours désormais résolu."""
    candidates: list[dict] = []
    for md_path in md_paths:
        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError:
            continue
        fm_raw, body = _split_frontmatter(text)
        if not fm_raw:
            continue
        fields = _parse_fm_lines(fm_raw)
        fm = dict(fields)
        notion_id = str(fm.get("notion_id", "") or "").strip()
        current_item = str(fm.get("item", "") or "").strip()
        if current_item or not notion_id or notion_id not in course_map:
            continue
        resolved = course_map[notion_id].display_item_number
        if resolved:
            candidates.append({"path": md_path, "fields": fields, "body": body, "item": resolved})
    return candidates


def apply_heal_candidate(candidate: dict) -> None:
    new_fm = _rebuild_fm(candidate["fields"], {"item": candidate["item"]})
    candidate["path"].write_text(new_fm + candidate["body"], encoding="utf-8")


async def main() -> None:
    apply_mode = "--apply" in sys.argv

    vault_path_str = settings.obsidian_vault_path
    if not vault_path_str:
        logger.error("obsidian_vault_path non configuré — rien à faire.")
        return

    vault = Path(vault_path_str)
    md_paths = list(vault.glob("01 - Cours EDN/*/Cours/*.md"))
    logger.info(f"{len(md_paths)} fiche(s) de cours trouvée(s) dans le vault.")

    logger.info("Récupération des cours Notion (état corrigé attendu)…")
    cours = await notion_service.get_all_cours()
    course_map = {c.id: c for c in cours}

    candidates = find_frontmatter_heal_candidates(md_paths, course_map)
    logger.info(f"{len(candidates)} fiche(s) à réparer.")

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {"candidates": [{"path": str(c["path"]), "item": c["item"]} for c in candidates]},
            f, ensure_ascii=False, indent=2,
        )

    if not apply_mode:
        print(f"\n[DRY RUN] {len(candidates)} fiche(s) seraient réparées.")
        print(f"Détail : {REPORT_PATH}")
        print("Relancer avec --apply pour écrire réellement dans le vault.")
        return

    healed = 0
    errors: list[dict] = []
    for candidate in candidates:
        try:
            apply_heal_candidate(candidate)
            healed += 1
        except OSError as e:
            logger.error(f"Échec réparation {candidate['path']}: {e}")
            errors.append({"path": str(candidate["path"]), "error": str(e)})

    print(f"\n=== Terminé ===")
    print(f"  réparées : {healed}/{len(candidates)}")
    print(f"  erreurs  : {len(errors)}")


if __name__ == "__main__":
    asyncio.run(main())
