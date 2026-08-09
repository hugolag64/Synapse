"""Shared semantic metric card model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricCard:
    label: str
    value: str
    helper: str = ""
    tone: str = "default"
