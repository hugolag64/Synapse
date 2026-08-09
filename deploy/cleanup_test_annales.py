"""Preview and optionally remove known test-only empty annale groups.

Usage inside the Synapse container::

    python -m deploy.cleanup_test_annales
    python -m deploy.cleanup_test_annales --apply

The default mode is read-only. The apply mode is deliberately narrow: it only
deletes empty groups whose source URL contains an explicit test marker.
"""

from __future__ import annotations

import argparse

from backend.core.reviews import local_store


TEST_URL_MARKERS = ("provenance-test-", "dossier-split-test")


def is_test_annale(row: dict) -> bool:
    """Return whether a row is an identifiable empty test artifact."""

    source_url = str(row.get("source_url") or "")
    total_parts = int(row.get("total_parts") or 0)
    return total_parts == 0 and any(marker in source_url for marker in TEST_URL_MARKERS)


def find_test_annales() -> list[dict]:
    """Find only empty, known test rows; never returns imported sessions."""

    return [row for row in local_store.list_uness_annales() if is_test_annale(row)]


def main(*, apply: bool = False) -> int:
    rows = find_test_annales()
    if not rows:
        print("Aucune annale de test vide détectée.")
        return 0

    print(f"{len(rows)} annale(s) de test vide(s) détectée(s) :")
    for row in rows:
        print(f"- id={row['id']} · {row['titre']} · {row['source_url']}")

    if not apply:
        print("Aucune suppression effectuée. Relancer avec --apply pour supprimer uniquement ces lignes.")
        return 0

    deleted = sum(1 for row in rows if local_store.delete_uness_annale(int(row["id"])))
    print(f"{deleted} annale(s) de test supprimée(s).")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="supprime les seules lignes de test vides détectées")
    raise SystemExit(main(apply=parser.parse_args().apply))
