"""scripts/backfill_uness_item_numbers.py — Synapse

Classe rétroactivement les sessions UNESS déjà importées sans item_number.
entrainement.uness.fr n'expose jamais lui-même de numéro d'item (seulement une
matière) — voir backend/core/uness/item_classifier.py pour le détail.

Dry-run par défaut : aucune écriture, aucun appel IA. --apply pour classer
réellement (appels Gemini flash-lite, quelques centimes pour tout l'arriéré).

Usage:
    python scripts/backfill_uness_item_numbers.py            # aperçu
    python scripts/backfill_uness_item_numbers.py --apply     # classe réellement
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.core.reviews import local_store
from backend.core.uness.item_classifier import classify_exam_items


def _pending_sessions() -> list[dict]:
    with local_store._conn() as con:
        rows = con.execute(
            """SELECT s.id, s.course_title, a.matiere
               FROM ai_practice_sessions s
               JOIN uness_annales a ON a.id = s.annale_id
               WHERE TRIM(COALESCE(s.item_number, '')) = ''
               ORDER BY s.id"""
        ).fetchall()
    return [dict(row) for row in rows]


def main() -> None:
    # Certaines matières/titres contiennent des emojis (référentiel collège) —
    # la console Windows par défaut (cp1252) ne les affiche pas.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Écrit réellement (sinon aperçu seul)")
    parser.add_argument("--delay", type=float, default=0.3, help="Pause entre appels IA (secondes)")
    args = parser.parse_args()

    pending = _pending_sessions()
    print(f"{len(pending)} session(s) UNESS importée(s) sans item_number.")
    if not pending:
        return
    if not args.apply:
        print("Aperçu seul (dry-run) — relance avec --apply pour classer réellement (appels Gemini flash-lite).")
        for row in pending[:10]:
            print(f"  #{row['id']:>4}  {row['matiere'] or '—':<25}  {row['course_title'][:70]}")
        if len(pending) > 10:
            print(f"  … et {len(pending) - 10} autre(s)")
        return

    tagged = skipped = 0
    for i, row in enumerate(pending, start=1):
        result = classify_exam_items(row["course_title"], row["matiere"] or "")
        if result.item_numbers:
            local_store.set_ai_practice_session_items(row["id"], result.item_numbers[0], result.item_numbers)
            tagged += 1
            print(f"[{i}/{len(pending)}] #{row['id']} {row['course_title'][:60]!r} -> {result.item_numbers}")
        else:
            skipped += 1
            print(f"[{i}/{len(pending)}] #{row['id']} {row['course_title'][:60]!r} -> non classifié")
        if i < len(pending):
            time.sleep(args.delay)

    print(f"Terminé : {tagged} classée(s), {skipped} non classifiée(s) (laissées vides pour révision manuelle).")


if __name__ == "__main__":
    main()
