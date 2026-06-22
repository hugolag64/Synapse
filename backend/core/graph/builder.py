"""
Graphe sémantique inter-fiches — Synapse F1
--------------------------------------------
Construit un graphe pondéré entre cours selon 4 règles :
  1. item_number partagé          → weight=1.0, type="same_item"
  2. même collège                 → weight=0.8, type="same_college"
  3. shared weak_point.category   → weight=0.6*(shared/max), type="shared_lacune"
  4. confusion QCM (raisonnement) → weight=0.9, type="qcm_confound"

Le graphe est stocké en mémoire dans data_store.semantic_graph et persisté
dans la table SQLite course_edges pour durabilité.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict

from loguru import logger

from backend.core.graph.models import CourseEdge


def build_semantic_graph(
    courses: list,
    weak_points: list,
    qcm_sessions: list | None = None,
) -> dict[str, list[CourseEdge]]:
    """
    Retourne {course_id: [CourseEdge]}.

    courses      : list[Cours] depuis data_store.cours
    weak_points  : list[dict] depuis local_store.get_active_weak_points()
    qcm_sessions : list[dict] optionnel depuis local_store.get_qcm_sessions_all()
    """
    graph: dict[str, list[CourseEdge]] = defaultdict(list)

    def _add(src: str, tgt: str, w: float, etype: str) -> None:
        graph[src].append(CourseEdge(src, tgt, w, etype))
        graph[tgt].append(CourseEdge(tgt, src, w, etype))

    # ── Règle 1 : même item_number ────────────────────────────────────────────
    item_groups: dict[str, list] = defaultdict(list)
    for c in courses:
        if c.item_number:
            item_groups[str(c.item_number).strip()].append(c)

    for _, group in item_groups.items():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                _add(a.id, b.id, 1.0, "same_item")

    # Mémoïser les paires déjà liées par same_item pour éviter les doublons
    same_item_pairs: set[tuple[str, str]] = set()
    for cid, edges in graph.items():
        for e in edges:
            if e.edge_type == "same_item":
                same_item_pairs.add((min(cid, e.target_id), max(cid, e.target_id)))

    # ── Règle 2 : même collège ────────────────────────────────────────────────
    college_groups: dict[str, list] = defaultdict(list)
    for c in courses:
        for col in (c.college or []):
            college_groups[col].append(c)

    for _, group in college_groups.items():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                pair = (min(a.id, b.id), max(a.id, b.id))
                if pair not in same_item_pairs:
                    _add(a.id, b.id, 0.8, "same_college")

    # ── Règle 3 : weak_point.category partagée ───────────────────────────────
    course_cats: dict[str, Counter] = defaultdict(Counter)
    for wp in weak_points:
        if isinstance(wp, dict):
            cat, cid = wp.get("category"), wp.get("course_id")
        else:
            cat, cid = getattr(wp, "category", None), getattr(wp, "course_id", None)
        if cat and cid:
            course_cats[cid][cat] += 1

    cids = list(course_cats.keys())
    for i, cid_a in enumerate(cids):
        for cid_b in cids[i + 1:]:
            shared = set(course_cats[cid_a]) & set(course_cats[cid_b])
            if not shared:
                continue
            max_cats = max(len(course_cats[cid_a]), len(course_cats[cid_b]))
            w = round(0.6 * (len(shared) / max_cats), 3)
            if w > 0:
                _add(cid_a, cid_b, w, "shared_lacune")

    # ── Règle 4 : confusion QCM (error_type='raisonnement', même date) ───────
    if qcm_sessions:
        date_to_courses: dict[str, list[str]] = defaultdict(list)
        for s in qcm_sessions:
            if isinstance(s, dict):
                sdate = s.get("session_date")
                cid   = s.get("course_id")
                etypes_raw = s.get("error_types", "[]")
            else:
                sdate = getattr(s, "session_date", None)
                cid   = getattr(s, "course_id", None)
                etypes_raw = getattr(s, "error_types", "[]")

            if isinstance(etypes_raw, str):
                etypes_raw = json.loads(etypes_raw or "[]")

            if sdate and cid and "raisonnement" in (etypes_raw or []):
                date_to_courses[sdate].append(cid)

        for _, cids_day in date_to_courses.items():
            seen: set[tuple[str, str]] = set()
            for i, cid_a in enumerate(cids_day):
                for cid_b in cids_day[i + 1:]:
                    pair = (min(cid_a, cid_b), max(cid_a, cid_b))
                    if pair not in seen:
                        seen.add(pair)
                        _add(cid_a, cid_b, 0.9, "qcm_confound")

    total_edges = sum(len(v) for v in graph.values())
    logger.info(
        f"Graphe sémantique : {len(graph)} nœuds, {total_edges} arêtes "
        f"(same_item/same_college/shared_lacune/qcm_confound)"
    )
    return dict(graph)
