"""Split one quiz out of a multi-quiz bridge into its own, ready-to-send file.

Useful when a bridge bundles several quizzes and the AI can't reliably process
all of them in one exchange (dropped or truncated content on the heaviest one).
Extracts that quiz's HTML (+ images + prompt) into a standalone bridge, and
removes it from the original so both stay unambiguous match targets for
import_service's title-based auto-matcher.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "quiz"


def split_bridge(bridge_path: Path, quiz_title: str, output_dir: Path) -> Path:
    bridge = json.loads(bridge_path.read_text(encoding="utf-8"))
    contents = bridge["contents"]
    matches = [content for content in contents if content["title"] == quiz_title]
    if not matches:
        available = [content["title"] for content in contents]
        raise ValueError(f"Quiz {quiz_title!r} introuvable. Titres disponibles : {available!r}")
    if len(matches) > 1:
        raise ValueError(f"Titre {quiz_title!r} ambigu dans ce bridge (plusieurs quiz portent ce nom)")
    quiz_content = matches[0]

    remaining = [content for content in contents if content is not quiz_content]
    if not remaining:
        raise ValueError("Ce bridge ne contient qu'un seul quiz : rien à séparer")

    split_payload = {**bridge, "contents": [quiz_content]}
    bridge["contents"] = remaining

    output_dir.mkdir(parents=True, exist_ok=True)
    split_path = output_dir / f"{bridge_path.stem}-{_slug(quiz_title.splitlines()[0])}.json"
    split_path.write_text(json.dumps(split_payload, ensure_ascii=False) + "\n", encoding="utf-8")
    bridge_path.write_text(json.dumps(bridge, ensure_ascii=False) + "\n", encoding="utf-8")
    return split_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Extraire un quiz volumineux d'un bridge UNESS multi-quiz")
    parser.add_argument("bridge_json", type=Path, help="Fichier bridge (UNESS/à_vérifier ou UNESS/archives)")
    parser.add_argument("quiz_title", help="Titre exact du quiz à extraire, ex: 'DP3\\nTest'")
    parser.add_argument(
        "--output-dir", type=Path, default=None, help="Défaut : même dossier que le bridge d'origine"
    )
    args = parser.parse_args()
    output_dir = args.output_dir or args.bridge_json.parent
    result = split_bridge(args.bridge_json, args.quiz_title, output_dir)
    print(result)


if __name__ == "__main__":
    main()
