"""
scripts/reconcile_colleges.py
------------------------------
Diagnostic en lecture seule : compare les PDFs présents localement sous
<medicine_dir>/Collèges/{collège}/item*/*.pdf avec les cours réellement
déclarés dans Notion (le champ Collège Notion fait foi — un item peut être
rattaché à plusieurs collèges).

Ne modifie rien. Affiche un résumé par collège et exporte le détail en JSON.

Usage :
    python scripts/reconcile_colleges.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from loguru import logger

from backend.config.settings import settings, NOTION_PROPS as P
from backend.core.files import resolve_college_folder
from backend.core.notion.client import notion_client
from backend.core.notion.service import notion_service
from backend.core.pdf_import import _extract_item_number
from backend.core.qcm.items_mapping import all_items

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reconcile_report.json")


async def reconcile() -> dict:
    medicine_dir = getattr(settings, "medicine_dir", None)
    if not medicine_dir or not os.path.isdir(medicine_dir):
        logger.error(f"medicine_dir non configuré ou introuvable : {medicine_dir!r}")
        sys.exit(1)

    colleges_root = os.path.join(medicine_dir, "Collèges")
    if not os.path.isdir(colleges_root):
        logger.error(f"Dossier introuvable : {colleges_root!r}")
        sys.exit(1)

    valid_items: dict[int, dict] = {item["item"]: item for item in all_items()}
    logger.info(f"{len(valid_items)} items EDN valides chargés")

    # ── Source de vérité : le champ Collège Notion ────────────────────────────
    logger.info("Récupération des cours Notion…")
    cours_existants = await notion_service.get_all_cours()

    # Certains cours n'ont le champ ITEM (number) vide et ne portent leur
    # numéro que via la relation ITEM lié — repli sur cette relation pour
    # ne pas les perdre du comparatif (cf. collège Endocrinologie).
    items_map: dict[int, str] = await notion_service.get_all_items_map()
    page_id_to_item_num: dict[str, int] = {v: k for k, v in items_map.items()}

    notion_by_item: dict[int, set[str]] = {}
    recovered_via_relation = 0
    for c in cours_existants:
        n: int | None = None
        try:
            n = int(float(c.item_number)) if c.item_number else None
        except (ValueError, TypeError):
            n = None
        if n is None and c.item_lie:
            n = page_id_to_item_num.get(c.item_lie)
            if n is not None:
                recovered_via_relation += 1
        if n:
            notion_by_item.setdefault(n, set()).update(c.college or [])
    logger.info(
        f"{len(cours_existants)} cours Notion — {len(notion_by_item)} numéros d'item distincts "
        f"({recovered_via_relation} récupérés via ITEM lié faute de champ ITEM rempli)"
    )

    db = await notion_client.retrieve_database(settings.notion.cours_db_id)
    notion_college_names = [
        o["name"] for o in db["properties"][P.COLLEGE]["multi_select"]["options"]
    ]

    # ── Scan local ──────────────────────────────────────────────────────────
    found: dict[int, dict[str, str]] = {}
    unresolved_folders: list[str] = []

    for folder_name in sorted(os.listdir(colleges_root)):
        folder_path = os.path.join(colleges_root, folder_name)
        if not os.path.isdir(folder_path):
            continue

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

        notion_college = resolve_college_folder(folder_name, notion_college_names)
        if notion_college is None:
            unresolved_folders.append(folder_name)
            logger.warning(f"Dossier non résolu vers un collège Notion : {folder_name!r}")
            continue

        for items_subdir in item_subdirs:
            try:
                pdf_files = [f for f in os.listdir(items_subdir) if f.lower().endswith(".pdf")]
            except OSError:
                continue

            for fname in pdf_files:
                item_num = _extract_item_number(fname)
                if item_num is None:
                    continue
                if item_num not in valid_items:
                    continue
                found.setdefault(item_num, {}).setdefault(notion_college, fname)

    # ── Comparaison ─────────────────────────────────────────────────────────
    gaps: list[dict] = []       # item existe dans Notion, mais pas rattaché à ce collège
    absent: list[dict] = []     # item n'existe dans Notion sous aucun collège

    for item_num, colleges_found in sorted(found.items()):
        notion_colleges = notion_by_item.get(item_num)
        title = valid_items[item_num]["title"]

        if notion_colleges is None:
            absent.append({
                "item": item_num,
                "title": title,
                "found_in_colleges": sorted(colleges_found.keys()),
                "source_files": colleges_found,
            })
            continue

        missing_colleges = sorted(set(colleges_found) - notion_colleges)
        if missing_colleges:
            gaps.append({
                "item": item_num,
                "title": title,
                "notion_colleges": sorted(notion_colleges),
                "missing_colleges": missing_colleges,
                "source_files": {c: colleges_found[c] for c in missing_colleges},
            })

    # ── Résumé par collège ──────────────────────────────────────────────────
    per_college: dict[str, dict] = {}
    for college in notion_college_names:
        local_items = {n for n, cols in found.items() if college in cols}
        notion_items = {n for n, cols in notion_by_item.items() if college in cols}
        per_college[college] = {
            "local_pdf_count": len(local_items),
            "notion_declared_count": len(notion_items),
            "missing_in_notion": sorted(local_items - notion_items),
        }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "colleges_root": colleges_root,
        "summary": {
            "total_pdfs_scanned": sum(len(c) for c in found.values()),
            "distinct_items_found_locally": len(found),
            "gaps": len(gaps),
            "absent": len(absent),
            "unresolved_folders": len(unresolved_folders),
        },
        "unresolved_folders": unresolved_folders,
        "gaps": gaps,
        "absent": absent,
        "per_college": per_college,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.success(f"Rapport exporté : {OUTPUT_PATH}")

    print("\n=== Résumé par collège ===")
    for college, stats in sorted(per_college.items()):
        flag = " ⚠" if stats["missing_in_notion"] else ""
        print(f"  {college:<45} local={stats['local_pdf_count']:>3}  notion={stats['notion_declared_count']:>3}{flag}")

    if unresolved_folders:
        print(f"\n=== Dossiers non résolus ({len(unresolved_folders)}) ===")
        for f in unresolved_folders:
            print(f"  - {f}")

    print(f"\n=== Écarts détectés ===")
    print(f"  gaps (item Notion existant, collège manquant) : {len(gaps)}")
    print(f"  absent (item introuvable dans Notion)          : {len(absent)}")

    return report


if __name__ == "__main__":
    asyncio.run(reconcile())
