"""
scripts/parse_nexternat.py
---------------------------
Parse la liste officielle des items EDN (nexternat.fr / UNESS) collée dans
scratchpad/nexternat_raw.txt en un mapping structuré item -> collèges
(écriture + relecture), avec extraction de l'acronyme officiel entre
parenthèses.

Ne touche pas à Notion. Sortie : data/nexternat_items.json
"""
from __future__ import annotations

import json
import os
import re
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

RAW_PATH = r"C:\Users\hugol\AppData\Local\Temp\claude\C--Users-hugol-Desktop-Projet-Python-Synapse\7ed13ee2-f937-4f0c-8f91-69556ac146ea\scratchpad\nexternat_raw.txt"
OUT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "nexternat_items.json")

COLLEGE_RE = re.compile(r"^(.*?)\s*\(([^()]+)\)$")


def split_colleges(raw: str) -> list[dict]:
    entries = []
    for part in raw.split(" • "):
        part = part.strip()
        if not part:
            continue
        m = COLLEGE_RE.match(part)
        if m:
            entries.append({"name": m.group(1).strip(), "acronym": m.group(2).strip()})
        else:
            entries.append({"name": part, "acronym": None})
    return entries


def parse() -> dict[int, dict]:
    lines = open(RAW_PATH, encoding="utf-8").read().splitlines()
    items: dict[int, dict] = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = re.split(r" {2,}", line)
        if not parts[0].isdigit():
            raise ValueError(f"Ligne inattendue (pas de numéro d'item) : {line[:80]!r}")
        item_num = int(parts[0])
        title = parts[1]
        ecriture_raw = parts[2] if len(parts) > 2 else ""
        relecture_raw = parts[3] if len(parts) > 3 else ""
        items[item_num] = {
            "item": item_num,
            "title": title,
            "ecriture": split_colleges(ecriture_raw),
            "relecture": split_colleges(relecture_raw),
        }
    return items


def main() -> None:
    items = parse()
    print(f"{len(items)} items parsés (attendu : 367)")

    acronyms: dict[str, set[str]] = {}
    for it in items.values():
        for c in it["ecriture"] + it["relecture"]:
            acronyms.setdefault(c["acronym"] or c["name"], set()).add(c["name"])

    print(f"{len(acronyms)} collèges distincts (par acronyme)")
    ambiguous = {a: names for a, names in acronyms.items() if len(names) > 1}
    if ambiguous:
        print("\n⚠ Acronymes avec plusieurs libellés différents :")
        for a, names in ambiguous.items():
            print(f"  {a}: {sorted(names)}")

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {"items": items, "colleges_by_acronym": {a: sorted(n)[0] for a, n in acronyms.items()}},
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\nÉcrit : {OUT_PATH}")

    print("\n=== Liste des collèges distincts (acronyme -> libellé nexternat) ===")
    for a in sorted(acronyms):
        print(f"  {a:<12} {sorted(acronyms[a])[0]}")


if __name__ == "__main__":
    main()
