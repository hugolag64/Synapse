"""Pure validation rules for college completion."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


REQUIRED_J_CYCLE = ("J3", "J7", "J14", "J30")


def _field(row: object, name: str, default: object = None) -> object:
    """Read a mapping-like or sqlite3.Row value without coupling this module."""

    if isinstance(row, Mapping):
        return row.get(name, default)
    try:
        return row[name]  # type: ignore[index]
    except (IndexError, KeyError, TypeError):
        return default


@dataclass(frozen=True)
class CollegeValidationReport:
    """Evidence-based validation report for one college."""

    college: str
    total_items: int
    evidence_item_ids: tuple[str, ...]
    missing_evidence_ids: tuple[str, ...]
    completed_j_cycle_ids: tuple[str, ...]
    missing_j_cycle_ids: tuple[str, ...]
    manual_status: str = "non_etudie"

    @property
    def automatic_ready(self) -> bool:
        """Whether the college can be proposed as automatically validated."""

        return (
            self.total_items > 0
            and not self.missing_evidence_ids
            and not self.missing_j_cycle_ids
        )

    @property
    def state_label(self) -> str:
        """Human-readable state for the college cockpit."""

        if self.manual_status == "valide":
            return "Confirmé manuellement"
        if self.automatic_ready:
            return "Validation automatique proposée"
        if self.manual_status == "en_cours":
            return "En cours"
        return "À compléter"


def assess_college_validation(
    college: str,
    courses: Iterable[object],
    item_states: Mapping[str, object],
    history: Mapping[str, Mapping[str, object]],
    manual_status: str = "non_etudie",
    history_by_course: Mapping[str, set[str]] | None = None,
    consolidation_counts: Mapping[str, int] | None = None,
) -> CollegeValidationReport:
    """Assess item evidence and consolidation.

    The function is intentionally read-only. A first-reading date or an
    existing item state is treated as evidence that the item has been seen,
    including items recovered from historical data.

    Consolidation was required as the *literal* J3/J7/J14/J30 spaced-repetition
    cycle marked done in review history — reachable by 0/44 colleges on real
    usage data, because annales and AI practice sessions never write to that
    cycle even though they are real consolidation. `consolidation_counts`
    (evidence per item, annales included — the same count `mastery.py` already
    uses for its score) is an alternative path to the same requirement: as
    many real touches as the cycle has steps (Q2).
    """

    course_list = list(courses)
    course_ids = tuple(str(course.id) for course in course_list)
    evidence_ids = tuple(
        sorted(
            course_id
            for course, course_id in zip(course_list, course_ids)
            if getattr(course, "date_1ere_lecture", None)
            or course_id in item_states
        )
    )
    missing_evidence_ids = tuple(
        sorted(set(course_ids).difference(evidence_ids))
    )

    if history_by_course is None:
        history_by_course = {}
        for row in history.values():
            course_id = str(_field(row, "course_id") or "")
            if (
                _field(row, "context") == "college"
                and _field(row, "status") == "done"
            ):
                history_by_course.setdefault(course_id, set()).add(
                    str(_field(row, "review_type"))
                )

    consolidation_counts = consolidation_counts or {}
    consolidation_required = len(REQUIRED_J_CYCLE)

    completed_j_cycle_ids: list[str] = []
    missing_j_cycle_ids: list[str] = []
    for course_id in course_ids:
        completed_types = history_by_course.get(course_id, set())
        touches = int(consolidation_counts.get(course_id, 0) or 0)
        if set(REQUIRED_J_CYCLE).issubset(completed_types) or touches >= consolidation_required:
            completed_j_cycle_ids.append(course_id)
        else:
            missing_j_cycle_ids.append(course_id)

    return CollegeValidationReport(
        college=college,
        total_items=len(course_ids),
        evidence_item_ids=evidence_ids,
        missing_evidence_ids=missing_evidence_ids,
        completed_j_cycle_ids=tuple(completed_j_cycle_ids),
        missing_j_cycle_ids=tuple(missing_j_cycle_ids),
        manual_status=manual_status,
    )
