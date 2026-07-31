"""Convert an explicit bridge + AI (ChatGPT/Gemini) response pair into canonical
vérifiés files.

`import_service.import_verified_directory` already auto-converts raw AI responses
dropped directly into `UNESS/vérifiés/`, matching them to a pending bridge file by
quiz title (see `backend/core/uness/gemini_conversion.py`). Use this script only
when you want to convert (and inspect) one pair explicitly, or when the bridge
can't be auto-matched unambiguously (e.g. two pending bridges share quiz titles).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.core.uness.gemini_conversion import convert_with_bridge  # noqa: E402
from backend.core.uness.import_service import assert_verified_exam  # noqa: E402
from backend.core.uness.json_io import save_exam  # noqa: E402


def _quiz_objects(chatgpt: Any) -> list[dict]:
    """Accept the current per-quiz prompt output (one object, or an array of them)
    as well as the legacy ChatGPT bundle shape (`{"contents": [{"title", "questions"}]}`)."""
    if isinstance(chatgpt, list):
        return chatgpt
    if "contents" in chatgpt:
        return [{"quiz_title": c["title"], "questions": c["questions"]} for c in chatgpt["contents"]]
    return [{"quiz_title": chatgpt["quiz_title"], "questions": chatgpt["questions"]}]


def convert(bridge_path: Path, chatgpt_path: Path, output_dir: Path) -> list[Path]:
    bridge = json.loads(bridge_path.read_text(encoding="utf-8"))
    chatgpt = json.loads(chatgpt_path.read_text(encoding="utf-8"))

    written: list[Path] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    for exam in convert_with_bridge(_quiz_objects(chatgpt), bridge):
        assert_verified_exam(exam)
        content_label = exam.title.rsplit(" — ", 1)[-1]
        target = output_dir / f"{re.sub(r'[^a-z0-9]+', '-', content_label.lower()).strip('-')}.json"
        save_exam(exam, target)
        written.append(target)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Convertir une réponse IA UNESS en fichiers vérifiés")
    parser.add_argument("bridge_json", type=Path, help="Fichier UNESS/à_vérifier envoyé à l'IA")
    parser.add_argument("chatgpt_json", type=Path, help="Réponse corrigée renvoyée par l'IA")
    parser.add_argument("--output-dir", type=Path, default=_ROOT / "UNESS" / "vérifiés")
    args = parser.parse_args()
    for path in convert(args.bridge_json, args.chatgpt_json, args.output_dir):
        print(path)


if __name__ == "__main__":
    main()
