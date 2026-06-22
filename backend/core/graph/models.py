from __future__ import annotations
from dataclasses import dataclass


@dataclass
class CourseEdge:
    source_id: str
    target_id: str
    weight: float       # 0..1
    edge_type: str      # "same_item" | "same_college" | "shared_lacune" | "qcm_confound"
