"""Repropose l'item EDN des sous-dossiers d'annales mal classés.

Contexte : à l'import, le classifieur d'items ne recevait que le titre de la
sous-partie et sa matière. Or `dp_context.enonce_general` est vide sur les
annales importées, et le titre porte le nom de l'examen — identique entre
sous-parties au suffixe près (« … — DP1 », « … — DP2 »). Résultat : toutes les
sous-parties d'un même examen recevaient le même item, alors qu'elles traitent
de dossiers cliniques différents.

Le correctif de `import_service._classification_context` règle le cas des
imports futurs. Ce script rejoue la classification sur les sessions déjà en
base, en lui donnant cette fois les premiers énoncés du dossier.

Cible par défaut : les groupes « suspects », c'est-à-dire les examens dont
toutes les sous-parties portent le même item — la signature du défaut.

Usage :
    ./.venv/Scripts/python.exe scripts/reclassify_annale_sessions.py           # simulation
    ./.venv/Scripts/python.exe scripts/reclassify_annale_sessions.py --apply   # écriture

La simulation n'écrit rien mais consomme des appels IA facturés (~0,0002 $ par
session) : c'est elle qui produit la proposition à relire.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

_DB = _ROOT / "data" / "synapse_local.db"
_SUBPART = re.compile(r"\s*[—-]\s*(DP|KFP|mDP|SQI|TCS)\s*\d*\s*$", re.IGNORECASE)
_STEMS = 4


def _exam_group(title: str) -> str:
    return _SUBPART.sub("", str(title or "")).strip()


def _load_sessions(con: sqlite3.Connection) -> list[dict]:
    rows = con.execute(
        """SELECT s.id, s.course_title, s.item_number, s.annale_id, a.matiere
           FROM ai_practice_sessions s
           LEFT JOIN uness_annales a ON a.id = s.annale_id
           WHERE s.annale_id IS NOT NULL
           ORDER BY s.id"""
    ).fetchall()
    return [
        {"id": r[0], "title": r[1], "item": r[2], "annale_id": r[3], "matiere": r[4] or ""}
        for r in rows
    ]


def _suspect_sessions(sessions: list[dict]) -> list[dict]:
    """Sous-parties d'un examen multi-parties partageant toutes le même item."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for session in sessions:
        groups[_exam_group(session["title"])].append(session)
    suspects: list[dict] = []
    for members in groups.values():
        if len(members) > 1 and len({m["item"] for m in members}) == 1:
            suspects.extend(members)
    return suspects


def _context_for(con: sqlite3.Connection, session_id: int) -> str:
    rows = con.execute(
        """SELECT q.prompt FROM ai_practice_session_questions sq
           JOIN ai_practice_questions q ON q.id = sq.question_id
           WHERE sq.session_id = ? ORDER BY sq.position LIMIT ?""",
        (session_id, _STEMS),
    ).fetchall()
    return "\n".join(str(r[0] or "").strip() for r in rows if str(r[0] or "").strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="écrit les items reproposés")
    parser.add_argument("--all", action="store_true", help="toutes les sessions d'annale, pas seulement les groupes suspects")
    parser.add_argument(
        "--link-orphans-from",
        metavar="SAUVEGARDE",
        help="crée les rattachements manquants des sessions dont l'item diffère de cette sauvegarde",
    )
    args = parser.parse_args()

    if args.link_orphans_from:
        return _link_orphans(Path(args.link_orphans_from), apply=args.apply)

    if not _DB.exists():
        raise SystemExit(f"Base introuvable : {_DB}")

    from backend.core.qcm.items_mapping import item_title
    from backend.core.uness.item_classifier import classify_exam_items

    with sqlite3.connect(f"file:{_DB}?mode=ro", uri=True) as con:
        sessions = _load_sessions(con)
        targets = sessions if args.all else _suspect_sessions(sessions)
        contexts = {s["id"]: _context_for(con, s["id"]) for s in targets}

    print(f"Sessions ciblées : {len(targets)}")
    print(f"Coût estimé      : ~{len(targets) * 0.00023:.3f} $\n")

    proposals: list[tuple[int, str, str, str]] = []
    for session in targets:
        context = contexts[session["id"]]
        if not context:
            print(f"  #{session['id']:<5} aucun énoncé exploitable, ignorée")
            continue
        result = classify_exam_items(session["title"], session["matiere"], context)
        proposed = result.item_numbers[0] if (result.confident and result.item_numbers) else ""
        current = str(session["item"] or "")
        mark = "=" if proposed == current else ("?" if not proposed else "→")
        print(
            f"  #{session['id']:<5} {mark} {current or '—':>4} → {proposed or 'non concluant':<14}"
            f" | {item_title(proposed)[:34] if proposed else '':<34} | {str(session['title'])[:44]}"
        )
        if proposed and proposed != current:
            proposals.append((session["id"], current, proposed, str(session["title"])))

    print(f"\nReclassements proposés : {len(proposals)} sur {len(targets)}")

    if not args.apply:
        print("\nSimulation seulement. Relance avec --apply pour écrire.")
        return 0

    if not proposals:
        print("Rien à écrire.")
        return 0

    from backend.core.reviews import local_store

    backup = _backup()
    print(f"\nSauvegarde : {backup}")

    # La maîtrise par item se calcule depuis `ai_practice_question_items`
    # (cf. backend/core/practice/item_evidence.py) et non depuis l'item de la
    # session : reclasser la seule session ne changerait rien à la statistique.
    # On ne remplace que les rattachements hérités de l'item de session ; ceux
    # issus de la migration par question du 3 août sont une classification plus
    # fine, déjà faite sur le contenu, et restent intacts.
    inherited = ("source-explicit-v1", "session-primary-v1")

    with sqlite3.connect(_DB) as con:
        touched_questions = 0
        for session_id, current, proposed, _title in proposals:
            con.execute(
                "UPDATE ai_practice_sessions SET item_number = ? WHERE id = ?",
                (proposed, session_id),
            )
            con.execute("DELETE FROM ai_practice_session_items WHERE session_id = ?", (session_id,))
            con.execute(
                "INSERT OR IGNORE INTO ai_practice_session_items(session_id, item_number) VALUES (?,?)",
                (session_id, proposed),
            )
            question_ids = [
                row[0]
                for row in con.execute(
                    "SELECT question_id FROM ai_practice_session_questions WHERE session_id = ?",
                    (session_id,),
                )
            ]
            for question_id in question_ids:
                cursor = con.execute(
                    f"""UPDATE ai_practice_question_items
                        SET item_number = ?
                        WHERE question_id = ? AND item_number = ?
                          AND classifier_version IN ({','.join('?' * len(inherited))})""",
                    (proposed, question_id, current, *inherited),
                )
                touched_questions += cursor.rowcount
                con.execute(
                    "UPDATE ai_practice_questions SET item_number = ? WHERE id = ? AND item_number = ?",
                    (proposed, question_id, current),
                )
        # Sans ligne dans `ai_practice_question_items`, une session jouée ne
        # produit aucune évidence de maîtrise (item_evidence.py fait la jointure
        # dessus). Les questions d'annale n'en avaient aucune : on la crée à
        # partir de l'item reclassé, qui vient cette fois du contenu du dossier.
        created_links = 0
        for session_id, _current, proposed, _title in proposals:
            orphans = [
                row[0]
                for row in con.execute(
                    """SELECT sq.question_id FROM ai_practice_session_questions sq
                       WHERE sq.session_id = ?
                         AND NOT EXISTS (SELECT 1 FROM ai_practice_question_items qi
                                         WHERE qi.question_id = sq.question_id)""",
                    (session_id,),
                )
            ]
            for question_id in orphans:
                con.execute(
                    """INSERT OR IGNORE INTO ai_practice_question_items
                       (question_id, item_number, confidence, source, classifier_version)
                       VALUES (?,?,?,?,?)""",
                    (question_id, proposed, 0.7, "reclassification", "annale-subpart-v1"),
                )
                created_links += 1
        con.commit()
    del local_store  # importé seulement pour garantir la présence du schéma

    print(
        f"{len(proposals)} session(s) reclassée(s), {touched_questions} rattachement(s) mis à jour, "
        f"{created_links} rattachement(s) créé(s)."
    )
    return 0


def _link_orphans(reference: Path, *, apply: bool) -> int:
    """Crée les rattachements manquants des sessions effectivement reclassées.

    Sans ligne dans `ai_practice_question_items`, une session jouée ne produit
    aucune évidence de maîtrise : la jointure de `item_evidence.py` porte sur
    cette table, pas sur l'item de la session. Les questions d'annale n'en ont
    aucune. On ne les crée que pour les sessions dont l'item a réellement changé
    — leur item vient désormais du contenu du dossier, pas d'un titre vide.
    """
    if not reference.exists():
        raise SystemExit(f"Sauvegarde de référence introuvable : {reference}")

    with sqlite3.connect(f"file:{reference}?mode=ro", uri=True) as ref:
        before = dict(ref.execute("SELECT id, item_number FROM ai_practice_sessions").fetchall())

    with sqlite3.connect(f"file:{_DB}?mode=ro", uri=True) as con:
        after = dict(con.execute("SELECT id, item_number FROM ai_practice_sessions").fetchall())
        changed = sorted(sid for sid, item in after.items() if before.get(sid) != item)
        orphans: dict[int, list[int]] = {}
        for session_id in changed:
            rows = con.execute(
                """SELECT sq.question_id FROM ai_practice_session_questions sq
                   WHERE sq.session_id = ?
                     AND NOT EXISTS (SELECT 1 FROM ai_practice_question_items qi
                                     WHERE qi.question_id = sq.question_id)""",
                (session_id,),
            ).fetchall()
            if rows:
                orphans[session_id] = [r[0] for r in rows]

    total = sum(len(v) for v in orphans.values())
    print(f"Sessions dont l'item a changé : {len(changed)}")
    print(f"Sessions avec des questions non rattachées : {len(orphans)}")
    print(f"Rattachements à créer : {total}\n")
    for session_id, questions in orphans.items():
        print(f"  #{session_id:<5} {before.get(session_id) or '—':>4} → {after[session_id]:<4} | {len(questions)} question(s)")

    if not apply:
        print("\nSimulation seulement. Relance avec --apply pour écrire.")
        return 0
    if not total:
        print("Rien à écrire.")
        return 0

    with sqlite3.connect(_DB) as con:
        for session_id, questions in orphans.items():
            for question_id in questions:
                con.execute(
                    """INSERT OR IGNORE INTO ai_practice_question_items
                       (question_id, item_number, confidence, source, classifier_version)
                       VALUES (?,?,?,?,?)""",
                    (question_id, after[session_id], 0.7, "reclassification", "annale-subpart-v1"),
                )
        con.commit()
    print(f"\n{total} rattachement(s) créé(s).")
    return 0


def _backup() -> Path:
    import datetime

    backup_dir = _DB.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = backup_dir / f"synapse_local-pre-reclass-{stamp}.db"
    source = sqlite3.connect(_DB)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
        target.commit()
    finally:
        target.close()
        source.close()
    return destination


if __name__ == "__main__":
    sys.exit(main())
