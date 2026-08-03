"""scripts/refine_uness_overbroad_items.py — Synapse

Recorrige les sessions UNESS dont la classification d'item (flash-lite,
scripts/backfill_uness_item_numbers.py) a probablement recopié presque toute
la liste de candidats de sa matière au lieu de discriminer réellement — signe
détecté quand le nombre d'items retenus s'approche du nombre total de
candidats disponibles pour cette matière.

Reclasse chaque question de ces sessions avec flash-lite à partir de son
énoncé. Une question n'est conservée que si la réponse est confiante et
contient au maximum deux items ; les cas plus larges restent à revoir.

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

from backend.core.reviews import local_store
from backend.core.uness.item_migration import MIGRATION_SOURCE, build_question_item_links
from backend.core.uness.item_classifier import candidate_items_for_college, classify_exam_items


def _suspect_sessions() -> list[dict]:
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
        if row["n_items"] >= 10:
            candidates = candidate_items_for_college(row["matiere"] or "")
            suspects.append({**dict(row), "n_candidates": len(candidates)})
    return suspects


def _session_questions(session_id: int) -> list[dict]:
    with local_store._conn() as con:
        rows = con.execute(
            """SELECT q.id, q.position, q.prompt
               FROM ai_practice_session_questions sq
               JOIN ai_practice_questions q ON q.id = sq.question_id
               WHERE sq.session_id = ?
               ORDER BY q.position, q.id""",
            (session_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _apply_session_links(session_id: int, classifications: dict[int, tuple[list[str], bool]]) -> tuple[int, int]:
    links = build_question_item_links(classifications)
    question_ids = list(classifications)
    item_numbers = sorted(
        {row[1] for row in links},
        key=lambda value: (int(value) if value.isdigit() else 10**9, value),
    )
    primary_item = item_numbers[0] if item_numbers else ""

    with local_store._conn() as con:
        for question_id in question_ids:
            con.execute(
                "DELETE FROM ai_practice_question_items WHERE question_id = ? AND source = ?",
                (question_id, MIGRATION_SOURCE),
            )
            con.execute("UPDATE ai_practice_questions SET item_number = '' WHERE id = ?", (question_id,))

        con.executemany(
            """INSERT OR IGNORE INTO ai_practice_question_items
               (question_id, item_number, confidence, source, classifier_version)
               VALUES (?, ?, ?, ?, ?)""",
            links,
        )
        for question_id, item_number, *_ in links:
            con.execute("UPDATE ai_practice_questions SET item_number = ? WHERE id = ?", (item_number, question_id))

        con.execute("DELETE FROM ai_practice_session_items WHERE session_id = ?", (session_id,))
        con.executemany(
            "INSERT OR IGNORE INTO ai_practice_session_items(session_id, item_number) VALUES (?, ?)",
            [(session_id, item_number) for item_number in item_numbers],
        )
        con.execute("UPDATE ai_practice_sessions SET item_number = ? WHERE id = ?", (primary_item, session_id))

    return len(links), len(item_numbers)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Recorrige réellement (sinon aperçu seul)")
    parser.add_argument("--delay", type=float, default=0.1, help="Pause entre appels IA (secondes)")
    args = parser.parse_args()

    suspects = _suspect_sessions()
    print(f"{len(suspects)} session(s) UNESS à reclasser (>=10 items historiques).")
    if not suspects:
        return
    if not args.apply:
        print("Aperçu seul (dry-run) — relance avec --apply pour reclasser question par question (flash-lite).")
        for row in suspects:
            print(f"  #{row['id']:>4}  {row['matiere'] or '—':<25}  {row['n_items']}/{row['n_candidates']} candidats  {row['course_title'][:55]}")
        return

    improved = unchanged = 0
    total_links = 0
    classification_cache: dict[int, tuple[list[str], bool]] = {}
    for i, row in enumerate(suspects, start=1):
        classifications = {}
        for question in _session_questions(row["id"]):
            if question["id"] not in classification_cache:
                result = classify_exam_items(
                    f"{row['course_title']} — question {question['position']}",
                    row["matiere"] or "",
                    context_text=question["prompt"] or "",
                )
                classification_cache[question["id"]] = (list(result.item_numbers), result.confident)
            classifications[question["id"]] = classification_cache[question["id"]]

        if not classifications:
            unchanged += 1
            print(f"[{i}/{len(suspects)}] #{row['id']} sans question exploitable")
        else:
            if args.apply:
                n_links, n_items = _apply_session_links(row["id"], classifications)
            else:
                dry_links = build_question_item_links(classifications)
                n_links = len(dry_links)
                n_items = len({row[1] for row in dry_links})
            total_links += n_links
            if n_items < row["n_items"]:
                improved += 1
            else:
                unchanged += 1
            print(f"[{i}/{len(suspects)}] #{row['id']} {row['n_items']} -> {n_items} items, {n_links} liens question-item")
        if i < len(suspects):
            time.sleep(args.delay)

    print(f"Terminé : {improved} session(s) resserrée(s), {unchanged} inchangée(s), {total_links} liens question-item acceptés.")


if __name__ == "__main__":
    main()
