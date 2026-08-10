"""Purge les lignes de télémétrie IA simulées par les tests.

Contexte : l'audit du 10 août 2026 a trouvé que `ai_usage_logs` mélangeait de vrais
appels facturés et des appels mockés écrits par la suite de tests. Tant que les deux
cohabitent, toute mesure de coût ou de fiabilité est fausse.

Le critère retenu est la **durée**. Un appel HTTP réel vers l'API Gemini ne peut pas
aboutir en moins d'une milliseconde ; un mock, si. Trois autres critères ont été
évalués puis écartés parce qu'ils capturaient de vrais appels :

- `context = 'unit_test'` : les 47 lignes concernées ont un coût réel.
- `context` finissant par « Test » : 139 lignes sur 149 sont de vraies corrections
  UNESS sur des annales dont le titre contient littéralement « Test ».
- coût nul **et** tokens nuls : inclut les 10 vrais échecs réseau (429, timeouts) qui
  constituent l'historique de fiabilité réel.

Usage :
    ./.venv/Scripts/python.exe scripts/purge_test_telemetry.py            # simulation
    ./.venv/Scripts/python.exe scripts/purge_test_telemetry.py --apply    # exécution
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_DB = _ROOT / "data" / "synapse_local.db"

# Une durée sous la milliseconde est impossible pour un aller-retour réseau réel.
_CRITERION = "duration_ms IS NOT NULL AND duration_ms < 1"


def _report(con: sqlite3.Connection) -> int:
    total = con.execute("SELECT COUNT(*) FROM ai_usage_logs").fetchone()[0]
    doomed = con.execute(f"SELECT COUNT(*) FROM ai_usage_logs WHERE {_CRITERION}").fetchone()[0]

    print(f"Base      : {_DB}")
    print(f"Total     : {total} lignes")
    print(f"À purger  : {doomed} ({doomed * 100 // total if total else 0} %)")
    print(f"Conservé  : {total - doomed}")
    print()

    print("Répartition des lignes à purger, par tâche :")
    for task, count, cost in con.execute(
        f"SELECT task, COUNT(*), COALESCE(SUM(cost_usd), 0) FROM ai_usage_logs "
        f"WHERE {_CRITERION} GROUP BY task ORDER BY 2 DESC"
    ):
        print(f"  {task or '(vide)':<28} {count:>5}  coût cumulé {cost:.6f} $")
    print()

    kept_cost = con.execute(
        f"SELECT COALESCE(SUM(cost_usd), 0) FROM ai_usage_logs WHERE NOT ({_CRITERION})"
    ).fetchone()[0]
    fastest_kept = con.execute(
        f"SELECT MIN(duration_ms) FROM ai_usage_logs WHERE NOT ({_CRITERION})"
    ).fetchone()[0]
    print(f"Coût réel conservé          : {kept_cost:.4f} $")
    print(f"Durée la plus courte gardée : {fastest_kept} ms")

    # Garde-fou : aucune ligne coûteuse ne doit tomber dans la purge.
    expensive = con.execute(
        f"SELECT COUNT(*) FROM ai_usage_logs WHERE {_CRITERION} AND cost_usd > 0.0001"
    ).fetchone()[0]
    if expensive:
        raise SystemExit(
            f"ABANDON : {expensive} ligne(s) à purger ont un coût significatif. "
            "Le critère capture de vrais appels, ne pas exécuter."
        )
    return doomed


def _backup_before_purge() -> Path:
    """Copie horodatée distincte de la sauvegarde quotidienne.

    `local_store.backup_database` nomme sa copie par date et s'arrête si elle
    existe déjà : elle rendrait l'état du matin, antérieur au travail du jour.
    """
    import datetime

    backup_dir = _DB.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = backup_dir / f"synapse_local-pre-purge-{stamp}.db"

    source = sqlite3.connect(_DB)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
        target.commit()
    finally:
        target.close()
        source.close()
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="exécute la suppression")
    args = parser.parse_args()

    if not _DB.exists():
        raise SystemExit(f"Base introuvable : {_DB}")

    if not args.apply:
        with sqlite3.connect(f"file:{_DB}?mode=ro", uri=True) as con:
            _report(con)
        print("\nSimulation seulement. Relance avec --apply pour exécuter.")
        return 0

    backup = _backup_before_purge()
    print(f"Sauvegarde : {backup}")

    with sqlite3.connect(_DB) as con:
        doomed = _report(con)
        con.execute(f"DELETE FROM ai_usage_logs WHERE {_CRITERION}")
        con.commit()
        remaining = con.execute("SELECT COUNT(*) FROM ai_usage_logs").fetchone()[0]

    print(f"\n{doomed} ligne(s) supprimée(s). {remaining} conservée(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
