"""Item-level invariants for mastery, evidence and planning."""

from datetime import datetime, date

from backend.core.knowledge import service as knowledge_service
from backend.core.reviews import local_store
from backend.core.reviews import mastery
from backend.core.reviews.models import ReviewTask
from backend.core.reviews.service import ReviewService
from backend.core.notion.models import Cours


def _course(course_id: str, *, item: str = "255", college: str = "Endocrinologie", pdf: str | None = "https://pdf") -> Cours:
    return Cours(
        id=course_id,
        title="Diabète gestationnel",
        item_number=item,
        college=[college],
        created_time=datetime(2026, 1, 1),
        url_pdf=pdf,
        date_1ere_lecture=date(2026, 1, 2),
        nb_lectures=1,
    )


def test_declared_seed_survives_missing_pdf_and_first_read():
    course = _course("declared-without-pdf", pdf=None)
    knowledge_service.ks.set_item_state(course.id, "correct", source="reprise")

    snapshot = mastery.get_course_mastery(course)

    assert snapshot.score is not None
    assert snapshot.evidence_count == 0
    assert snapshot.declared_level == "correct"
    assert snapshot.level in {"fragile", "à consolider", "critique"}


def test_item_mastery_is_identical_from_each_fiche(monkeypatch):
    first = _course("fiche-255-a", college="Endocrinologie")
    second = _course("fiche-255-b", college="Pédiatrie")
    from backend.state.store import data_store

    monkeypatch.setattr(data_store, "cours", [first, second])
    data_store._alias_map = None
    data_store._alias_signature = -1

    first_snapshot = mastery.get_item_mastery(first.id)
    second_snapshot = mastery.get_item_mastery(second.id)

    assert first_snapshot.score == second_snapshot.score
    assert first_snapshot.evidence_count == second_snapshot.evidence_count
    assert first_snapshot.course_id == second_snapshot.course_id


def test_item_sessions_are_aggregated_across_all_fiches(monkeypatch):
    first = _course("fiche-255-a", college="Endocrinologie")
    second = _course("fiche-255-b", college="Pédiatrie")
    from backend.state.store import data_store

    monkeypatch.setattr(data_store, "cours", [first, second])
    data_store._alias_map = None
    data_store._alias_signature = -1
    monkeypatch.setattr(
        local_store,
        "get_sessions_by_course",
        lambda: {"fiche-255-a": [{"id": "a"}], "fiche-255-b": [{"id": "b"}]},
    )

    sessions = mastery.get_item_sessions(first.id)

    assert {row["id"] for row in sessions} == {"a", "b"}


def test_item_detail_activity_is_aggregated_across_all_fiches(monkeypatch):
    first = _course("fiche-255-a", college="Endocrinologie")
    second = _course("fiche-255-b", college="Pédiatrie")
    from backend.state.store import data_store

    monkeypatch.setattr(data_store, "cours", [first, second])
    data_store._alias_map = None
    data_store._alias_signature = -1
    monkeypatch.setattr(
        local_store,
        "get_qcm_sessions_by_course",
        lambda course_id: [{"id": f"qcm-{course_id}"}],
    )
    monkeypatch.setattr(
        local_store,
        "get_weak_points_for_course",
        lambda course_id: [{"id": f"weak-{course_id}"}],
    )
    monkeypatch.setattr(
        local_store,
        "get_review_history_by_course",
        lambda course_id: [{"id": f"history-{course_id}", "review_type": "J3"}],
    )

    assert {row["id"] for row in mastery.get_item_qcm_sessions(first.id)} == {
        "qcm-fiche-255-a", "qcm-fiche-255-b"
    }
    assert {row["id"] for row in mastery.get_item_weak_points(first.id)} == {
        "weak-fiche-255-a", "weak-fiche-255-b"
    }
    assert {row["id"] for row in mastery.get_item_review_history(first.id)} == {
        "history-fiche-255-a", "history-fiche-255-b"
    }


def test_item_tasks_are_unique_across_fiches(monkeypatch):
    service = ReviewService()
    tasks = [
        ReviewTask(
            id="a", course_id="fiche-a", course_title="A", item_number="255",
            theoretical_due_date=date.today(), due_date=date.today(), review_type="J3",
        ),
        ReviewTask(
            id="b", course_id="fiche-b", course_title="B", item_number="255",
            theoretical_due_date=date.today(), due_date=date.today(), review_type="J7",
        ),
        ReviewTask(
            id="c", course_id="fiche-c", course_title="C", item_number="256",
            theoretical_due_date=date.today(), due_date=date.today(), review_type="J3",
        ),
    ]
    monkeypatch.setattr(service, "generate_reviews", lambda *args, **kwargs: tasks)

    result = service.get_tasks_for_item("255")

    assert len(result) == 1
    assert result[0].item_number == "255"


def test_oic_without_attempt_is_not_zero_percent():
    local_store.upsert_lisa_oic("unmeasured-oic-item", [
        {"oic_code": "OIC-255-A", "intitule": "Objectif", "rang": "A"},
    ])

    coverage = knowledge_service.oic_coverage("unmeasured-oic-item")

    assert coverage["rang_a_conclusive"] is False
    assert coverage["rang_a_pct_attempted"] is None
