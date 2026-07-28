from __future__ import annotations

import re

_ROOT = "Fiches EDN Notion::"
_ITEM_DECK_RE = re.compile(r"^(?P<numbers>\d+(?:\s*,\s*\d+)*)\s*\.")


def parse_item_numbers(deck_name: str) -> tuple[str, ...]:
    if not deck_name.startswith(_ROOT):
        return ()
    leaf = deck_name.rsplit("::", 1)[-1].strip()
    match = _ITEM_DECK_RE.match(leaf)
    if not match:
        return ()
    return tuple(number.strip() for number in match.group("numbers").split(","))
