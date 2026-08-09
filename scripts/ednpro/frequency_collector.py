"""CLI for the low-cost EDNpro /training-v2 frequency snapshot."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:  # Allow direct execution from the repository root.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.core.ednpro.frequency_sync import sync_if_due


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchroniser les fréquences EDNpro")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Exécuter Chromium sans interface graphique (défaut serveur)",
    )
    parser.add_argument(
        "--headed",
        action="store_false",
        dest="headless",
        help="Afficher Chromium pour une authentification interactive",
    )
    parser.add_argument("--profile-dir", type=Path, default=Path("data/ednpro/browser-profile"))
    parser.add_argument("--cdp-url", help="S'attacher à un Chrome normal déjà ouvert")
    args = parser.parse_args()
    result = asyncio.run(
        sync_if_due(
            profile_dir=args.profile_dir,
            force=args.force,
            headless=args.headless,
            cdp_url=args.cdp_url,
        )
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
