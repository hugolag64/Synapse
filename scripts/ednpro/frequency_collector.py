"""CLI for the low-cost EDNpro /training-v2 frequency snapshot."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from backend.core.ednpro.frequency_sync import sync_if_due


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchroniser les fréquences EDNpro")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--profile-dir", type=Path, default=Path("data/ednpro/browser-profile"))
    args = parser.parse_args()
    result = asyncio.run(sync_if_due(profile_dir=args.profile_dir, force=args.force, headless=args.headless))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
