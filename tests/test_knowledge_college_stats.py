"""Tests du contrat courant du cockpit Collèges.

Les anciens tests ciblaient ``frontend.pages.colleges._compute_stats``. Cette
page est désormais un redirecteur ; les agrégats sont portés par les helpers
du cockpit.
"""
from types import SimpleNamespace

from frontend.pages.colleges_cockpit import _college_item_rows, _pilotage_summary, count_no_pdf


def _course(course_id: str, item_number: str, started: bool):
    return SimpleNamespace(
        id=course_id,
        item_number=item_number,
        title=f"Cours {item_number}",
        date_1ere_lecture="2026-01-01" if started else None,
        url_pdf="https://example.test/item.pdf",
    )


def test_college_item_rows_represente_les_items_non_commences():
    rows = _college_item_rows(
        [_course("course-1", "1", False)],
        [],
    )

    assert rows[0]["level"] == "non_commence"
    assert rows[0]["pct"] == 0
    assert rows[0]["urgent"] is False


def test_college_item_rows_reprend_la_maitrise_et_la_prochaine_revision():
    task = SimpleNamespace(course_id="course-1", due_date=__import__("datetime").date.today())
    rows = _college_item_rows(
        [_course("course-1", "1", True)],
        [task],
        mastery_by_course={"course-1": (72, "à consolider")},
        urgent_ids={"course-1"},
        qcm_map={"course-1": {"last_score": 80}},
    )

    assert rows[0]["score"] == 72
    assert rows[0]["level"] == "à consolider"
    assert rows[0]["urgent"] is True
    assert rows[0]["next_task"] is task
    assert rows[0]["qcm_score"] == 80


def test_pilotage_summary_agrege_les_cours_et_les_retards():
    summary = _pilotage_summary([
        {"total": 3, "started": 2, "retard": 1, "fragile": 1, "no_pdf": False, "pct": 2 / 3},
        {"total": 2, "started": 0, "retard": 0, "fragile": 0, "no_pdf": True, "pct": 0},
    ])

    assert summary["total_courses"] == 5
    assert summary["started"] == 2
    assert summary["pct"] == 2 / 5
    assert summary["overdue"] == 1
    assert summary["no_pdf"] == 1


def test_pilotage_summary_expose_les_niveaux_et_la_charge():
    summary = _pilotage_summary([
        {"total": 2, "started": 2, "retard": 0, "fragile": 0, "no_pdf": False, "pct": 1.0},
        {"total": 1, "started": 0, "retard": 0, "fragile": 1, "no_pdf": False, "pct": 0.0},
    ])

    assert summary["level_counts"]["solide"] == 1
    assert summary["level_counts"]["non_commence"] == 1
    assert summary["estimated_minutes"] == 20


def test_no_pdf_compte_les_fiches_sans_pdf():
    courses = [
        _course("a", "1", False),
        _course("b", "2", False),
    ]
    courses[0].url_pdf = ""

    assert count_no_pdf(courses) == 1


def test_pilotage_ne_compte_pas_deux_fois_une_fiche_multi_colleges_sans_pdf():
    rows = [
        {
            "item_ids": {"item-1"},
            "no_pdf_course_ids": {"fiche-1"},
            "total": 1,
            "started": 0,
            "retard": 0,
            "fragile": 0,
            "no_pdf": True,
        },
        {
            "item_ids": {"item-1"},
            "no_pdf_course_ids": {"fiche-1"},
            "total": 1,
            "started": 0,
            "retard": 0,
            "fragile": 0,
            "no_pdf": True,
        },
    ]

    assert _pilotage_summary(rows)["no_pdf"] == 1
