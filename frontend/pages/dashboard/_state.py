"""
DashboardState — état partagé du dashboard Synapse.
Passé par référence à chaque module dashboard pour partager
les refs NiceGUI et les compteurs sans closures imbriquées.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class DashboardState:
    # ── Contexte & filtres ────────────────────────────────────────────────────
    review_context: str = "college"
    done_today_count: int = 0
    college_filter: Optional[str] = None

    # ── Mode Focus ────────────────────────────────────────────────────────────
    focus_tasks: list = field(default_factory=list)
    focus_cache: dict = field(default_factory=lambda: {"qcm": {}, "lac": {}})

    # ── Refs NiceGUI (peuplées après construction) ────────────────────────────
    banner_refs: dict = field(default_factory=dict)
    hero_container: Any = None
    agenda_col: Any = None
    smart_lbl: Any = None
    monday_container: Any = None
    urgent_col: Any = None
    today_col: Any = None
    week_col: Any = None
    college_filter_row: Any = None
    college_chip_refs: dict = field(default_factory=dict)

    # ── Refs colonnes révision ────────────────────────────────────────────────
    urgent_count_lbl: Any = None
    today_count_lbl: Any = None
    retard_header: Any = None
    today_header: Any = None

    # ── Callback _rebuild_all (injecté par __init__.py) ───────────────────────
    rebuild_all: Any = None   # callable() → None
