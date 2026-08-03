"""scripts/refine_uness_overbroad_items.py — Synapse

Recorrige les sessions UNESS dont la classification d'item (flash-lite,
scripts/backfill_uness_item_numbers.py) a probablement recopié presque toute
la liste de candidats de sa matière au lieu de discriminer réellement — signe
détecté quand le nombre d'items retenus s'approche du nombre total de
candidats disponibles pour cette matière.

Relance uniquement ces sessions suspectes avec le modèle Flash (plus fiable
sur les longues listes) et un prompt durci contre la sur-inclusion.

Dry-run par défaut : liste les sessions suspectes, aucune écriture, aucun appel IA.
--apply : reclassifie réellement et remplace leur liste d'items.

Usage:
    python scripts/refine_uness_overbroad_items.py            # aperçu
    python scripts/refine_uness_overbroad_items.py --apply     # recorrige réellement
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.core.ai.routing import AIModel
from backend.core.reviews import local_store
from backend.core.uness.item_classifier import candidate_items_for_college, classify_exam_items


def _suspect_sessions(min_pool: int = 5) -> list[dict]:
    with local_store._conn() as con:
        rows = con.execute(
            """SELECT s.id, s.course_title, a.matiere,
                      (SELECT COUNT(*) FROM ai_practice_session_items i WHERE i.session_id = s.id) AS n_items
               FROM ai_practice_sessions s
               JOIN uness_annales a ON a.id = s.annale_id
               WHERE s.id IN (SELECT session_id FROM ai_practice_session_items)
               ORDER BY s.id"""
        ).fetchall()

    suspects = []
    for row in rows:
        candidates = candidate_items_for_college(row["matiere"] or "")
        if len(candidates) >= min_pool and row["n_items"] >= max(1, len(candidates) - 1):
            suspects.append({**dict(row), "n_candidates": len(candidates)})
    return suspects


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Recorrige réellement (sinon aperçu seul)")
    parser.add_argument("--delay", type=float, default=0.3, help="Pause entre appels IA (secondes)")
    args = parser.parse_args()

    suspects = _suspect_sessions()
    print(f"{len(suspects)} session(s) suspecte(s) (items ≈ tous les candidats de la matière).")
    if not suspects:
        return
    if not args.apply:
        print("Aperçu seul (dry-run) — relance avec --apply pour recorriger réellement (modèle Flash).")
        for row in suspects:
            print(f"  #{row['id']:>4}  {row['matiere'] or '—':<25}  {row['n_items']}/{row['n_candidates']} candidats  {row['course_title'][:55]}")
        return

    improved = unchanged = 0
    for i, row in enumerate(suspects, start=1):
        result = classify_exam_items(
            row["course_title"], row["matiere"] or "", force_model=AIModel.FLASH,
        )
        if result.item_numbers and len(result.item_numbers) < row["n_items"]:
            local_store.set_ai_practice_session_items(row["id"], result.item_numbers[0], result.item_numbers)
            improved += 1
            print(f"[{i}/{len(suspects)}] #{row['id']} {row['n_items']} -> {len(result.item_numbers)} items : {result.item_numbers}")
        else:
            unchanged += 1
            print(f"[{i}/{len(suspects)}] #{row['id']} confirmé large ({row['n_items']} items) : {result.item_numbers}")
        if i < len(suspects):
            time.sleep(args.delay)

    print(f"Terminé : {improved} resserrée(s), {unchanged} confirmée(s) large(s) (probablement légitimement transverses).")


if __name__ == "__main__":
    main()
