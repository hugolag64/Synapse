from datetime import date
import sqlite3
from types import SimpleNamespace

from backend.core.knowledge.college_validation import assess_college_validation


def _course(course_id: str, first_read=None):
    return SimpleNamespace(id=course_id, date_1ere_lecture=first_read)


def _history(course_id: str, review_types: tuple[str, ...]):
    return {
        f"{course_id}_college_{review_type}": {
            "course_id": course_id,
            "context": "college",
            "review_type": review_type,
            "status": "done",
        }
        for review_type in review_types
    }


def test_auto_validation_requires_evidence_and_complete_j_cycle():
    courses = [_course("c1", date(2026, 1, 1)), _course("c2")]
    states = {"c2": SimpleNamespace(source="reprise_historique")}
    history = _history("c1", ("J3", "J7", "J14", "J30"))
    history.update(_history("c2", ("J3", "J7", "J14", "J30")))

    report = assess_college_validation("Cardio", courses, states, history)

    assert report.automatic_ready is True
    assert report.missing_evidence_ids == ()
    assert report.missing_j_cycle_ids == ()
    assert report.manual_status == "non_etudie"


def test_report_explains_missing_evidence_and_j_cycle():
    courses = [_course("c1", date(2026, 1, 1)), _course("c2")]
    history = _history("c1", ("J3", "J7", "J14"))

    report = assess_college_validation("Cardio", courses, {}, history)

    assert report.automatic_ready is False
    assert report.missing_evidence_ids == ("c2",)
    assert report.missing_j_cycle_ids == ("c1", "c2")


def test_manual_validation_is_kept_even_when_proof_is_incomplete():
    report = assess_college_validation(
        "Cardio", [_course("c1")], {}, {}, manual_status="valide"
    )

    assert report.manual_status == "valide"
    assert report.state_label == "Confirmé manuellement"
    assert report.automatic_ready is False


def test_consolidation_evidence_can_replace_the_literal_j_cycle():
    """Le cycle J3/J7/J14/J30 littéral n'était jamais atteint sur données
    réelles (0/44 collèges) : les annales et sessions IA sont des preuves de
    consolidation réelles qui ne l'alimentent jamais. Autant de preuves que
    le cycle a d'étapes (4) suffit désormais, quelle que soit leur nature
    (Q2)."""
    courses = [_course("c1", date(2026, 1, 1)), _course("c2", date(2026, 1, 1))]

    report = assess_college_validation(
        "Cardio", courses, {}, {}, consolidation_counts={"c1": 4, "c2": 2},
    )

    assert report.missing_j_cycle_ids == ("c2",)
    assert "c1" in report.completed_j_cycle_ids


def test_report_accepts_sqlite_rows_from_review_history():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        "CREATE TABLE history (course_id TEXT, context TEXT, review_type TEXT, status TEXT)"
    )
    for review_type in ("J3", "J7", "J14", "J30"):
        connection.execute(
            "INSERT INTO history VALUES (?, ?, ?, ?)",
            ("c1", "college", review_type, "done"),
        )
    connection.commit()
    rows = connection.execute("SELECT rowid AS id, * FROM history").fetchall()

    report = assess_college_validation(
        "Cardio", [_course("c1", date(2026, 1, 1))], {}, {str(i): row for i, row in enumerate(rows)}
    )

    assert report.automatic_ready is True
