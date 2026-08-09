"""Reprise locale des collèges déjà validés avant Synapse.

Le script ne modifie pas Notion. Il ajoute uniquement les informations locales
nécessaires pour que les cours historiques rejoignent la boucle de consolidation
à partir du 20 août 2026.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Iterable, Mapping, Sequence


# Permet l'exécution directe depuis la racine du dépôt ou le conteneur :
# ``python deploy/reprise_historique_consolidation.py --dry-run``.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


TARGET_COLLEGES = frozenset({
    "Cardiovasculaire ❤️",
    "Dermatologie 🧴",
    "Endocrinologie - Diabétologie - Maladies métaboliques 🫘",
    "Hépato-Gastro-entérologie 🧻",
    "Infectiologie 🦠",
    "Neurochirurgie 🧠",
    "Neurologie 🧠",
    "Nutrition 🍔",
    "Néphrologie 🧑‍🔬",
    "Pneumologie 🫁",
})
START_DATE = datetime.date(2026, 8, 20)
DEFAULT_LEVEL = "correct"
SOURCE = "reprise_historique"


def get_target_courses(courses: Iterable) -> list:
    """Retourne les cours ciblés, dédupliqués et dans l'ordre du cache."""
    selected = []
    seen: set[str] = set()
    for course in courses:
        if not TARGET_COLLEGES.intersection(getattr(course, "college", None) or []):
            continue
        if course.id not in seen:
            selected.append(course)
            seen.add(course.id)
    return selected


def get_missing_state_course_ids(
    courses: Iterable,
    states: Mapping[str, object],
    college_statuses: Mapping[str, str] | None = None,
) -> list[str]:
    """Sélectionne les états manquants sans toucher aux niveaux existants."""
    del college_statuses  # Les cours des dix collèges sont ciblés même avant leur statut local.
    return [course.id for course in get_target_courses(courses) if course.id not in states]


def build_report(
    courses: Sequence,
    states: Mapping[str, object],
    college_statuses: Mapping[str, str],
) -> dict:
    """Construit le rapport lisible par l'humain et par une vérification shell."""
    target_courses = get_target_courses(courses)
    target_assignments = [
        (course.id, college)
        for course in target_courses
        for college in (getattr(course, "college", None) or [])
        if college in TARGET_COLLEGES
    ]
    missing_ids = get_missing_state_course_ids(courses, states, college_statuses)
    missing_assignment_count = sum(
        course_id not in states for course_id, _college in target_assignments
    )
    missing_statuses = sorted(
        college for college in TARGET_COLLEGES
        if college_statuses.get(college) != "valide"
    )
    courses_by_college = {
        college: [
            course.id for course in target_courses
            if college in (getattr(course, "college", None) or [])
        ]
        for college in sorted(TARGET_COLLEGES)
    }
    existing_count = len(target_courses) - len(missing_ids)
    return {
        "start_date": START_DATE.isoformat(),
        "target_college_count": len(TARGET_COLLEGES),
        "target_colleges": sorted(TARGET_COLLEGES),
        "target_course_count": len(target_courses),
        "target_course_assignment_count": len(target_assignments),
        "courses_by_college": courses_by_college,
        "existing_item_state_count": existing_count,
        "missing_item_state_count": len(missing_ids),
        "missing_item_state_assignment_count": missing_assignment_count,
        "missing_item_state_ids": sorted(missing_ids),
        "default_missing_level": DEFAULT_LEVEL,
        "colleges_needing_validation": missing_statuses,
        "planned_status_update_count": len(missing_statuses),
        "planned_gate_count": len(target_courses),
    }


def apply_reprise(
    courses: Sequence,
    states: Mapping[str, object],
    college_statuses: Mapping[str, str],
) -> dict:
    """Applique la reprise après création d'une sauvegarde SQLite."""
    from backend.core.knowledge import store as knowledge_store
    from backend.core.reviews import local_store
    from backend.core.reviews.consolidation import (
        DEFAULT_INITIAL_INTERVAL,
        INITIAL_INTERVAL_BY_LEVEL,
    )
    from backend.core.reviews.mastery import get_course_mastery

    backup_path = local_store.backup_database()
    if backup_path is None:
        raise RuntimeError("Impossible de créer la sauvegarde SQLite avant --apply")

    target_courses = get_target_courses(courses)
    missing_statuses = sorted(
        college for college in TARGET_COLLEGES
        if college_statuses.get(college) != "valide"
    )
    for college in missing_statuses:
        knowledge_store.set_college_status(college, "valide")

    missing_ids = get_missing_state_course_ids(courses, states, college_statuses)
    for course_id in missing_ids:
        knowledge_store.set_item_state(
            course_id, DEFAULT_LEVEL, context="college", source=SOURCE,
        )

    gates_written = 0
    bootstraps_created = 0
    for course in target_courses:
        local_store.set_consolidation_not_before(
            course.id, "college", START_DATE, source=SOURCE,
        )
        gates_written += 1

        if local_store.get_last_consolidation_state(course.id, "college") is not None:
            continue

        mastery = get_course_mastery(course, context="college")
        initial_interval = INITIAL_INTERVAL_BY_LEVEL.get(
            mastery.level, DEFAULT_INITIAL_INTERVAL,
        )
        anchor = START_DATE - datetime.timedelta(days=initial_interval)
        local_store.bootstrap_consolidation(
            course.id,
            "college",
            course.title,
            course.item_number or "",
            initial_interval,
            anchor,
        )
        if local_store.get_last_consolidation_state(course.id, "college") is not None:
            bootstraps_created += 1

    return {
        "backup_path": str(backup_path),
        "target_course_count": len(target_courses),
        "status_updates": len(missing_statuses),
        "item_states_created": len(missing_ids),
        "gates_written": gates_written,
        "bootstraps_created": bootstraps_created,
        "start_date": START_DATE.isoformat(),
    }


def _load_runtime() -> tuple[list, dict, dict]:
    from backend.core.knowledge import store as knowledge_store
    from backend.state.store import data_store

    if not data_store.load_from_disk(force=True):
        raise RuntimeError("Cache local data_cache.json introuvable ou illisible")
    return (
        list(data_store.cours),
        knowledge_store.get_all_item_states("college"),
        knowledge_store.get_all_college_statuses(),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    courses, states, statuses = _load_runtime()
    if args.dry_run:
        print(json.dumps(build_report(courses, states, statuses), ensure_ascii=False, indent=2))
        return 0

    print(json.dumps(apply_reprise(courses, states, statuses), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
