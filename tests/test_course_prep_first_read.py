import datetime as dt

import pytest

from backend.core.prep.service import validate_prep_task
from backend.core.prep.store import get_learning_schedule, upsert_prep_task
from backend.core.reviews import local_store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "prep-first-read.sqlite3"
    monkeypatch.setattr(local_store, "DB_PATH", db_path)
    local_store._DB = None
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    local_store._DB = None


def test_validating_first_read_anchors_all_local_review_dates_to_lecture_day():
    task = upsert_prep_task(
        "course-363", "363", dt.date(2026, 8, 28), "event-1", "Item 363", "first_read"
    )

    validated = validate_prep_task(task.id)
    schedule = get_learning_schedule("course-363")

    assert validated.status == "done"
    assert schedule is not None
    assert schedule.first_read_date == dt.date(2026, 8, 28)
    assert schedule.j1_date == dt.date(2026, 8, 29)
    assert schedule.j3_date == dt.date(2026, 8, 31)
    assert schedule.j7_date == dt.date(2026, 9, 4)
    assert schedule.j14_date == dt.date(2026, 9, 11)
    assert schedule.j30_date == dt.date(2026, 9, 27)


def test_cancelled_first_read_cannot_be_validated():
    task = upsert_prep_task(
        "course-363", "363", dt.date(2026, 8, 28), "event-1", "Item 363", "first_read"
    )
    from backend.core.prep.store import update_prep_task_status

    update_prep_task_status(task.id, "cancelled")
    with pytest.raises(ValueError, match="annulée"):
        validate_prep_task(task.id)


def test_anchoring_a_first_read_from_a_view_plans_the_whole_cycle():
    """Sans date de référence, le moteur ne génère aucune révision : l'action
    « Commencer » des vues Items/Collèges/fiche pose le cycle localement."""
    from backend.core.prep.service import anchor_first_read

    schedule = anchor_first_read("fiche-42", dt.date(2026, 8, 19))

    assert schedule.first_read_date == dt.date(2026, 8, 19)
    assert schedule.j1_date == dt.date(2026, 8, 20)
    assert schedule.j30_date == dt.date(2026, 9, 18)
    assert get_learning_schedule("fiche-42") is not None


def test_anchoring_defaults_to_today_and_refuses_an_empty_course():
    from backend.core.prep.service import anchor_first_read

    schedule = anchor_first_read("fiche-43")

    assert schedule.first_read_date == dt.date.today()
    with pytest.raises(ValueError):
        anchor_first_read("")


def test_an_anchored_cycle_counts_as_a_first_read_for_mastery():
    """Sans cela, l'item reste « à préparer », score None, et le moteur refuse
    de planifier ses révisions : l'action « Commencer » serait sans effet."""
    from types import SimpleNamespace

    from backend.core.knowledge.item_progress import invalidate_schedule_cache
    from backend.core.knowledge.store import init_knowledge_tables
    from backend.core.prep.service import anchor_first_read
    from backend.core.reviews.mastery import get_course_mastery

    init_knowledge_tables()  # la base isolée du module n'a pas encore item_state

    course = SimpleNamespace(
        id="fiche-44", title="Item 44", item_number="44", college=["Gynécologie"],
        url_pdf=None, url_pdf_ue=None, date_1ere_lecture=None, date_1ere_lecture_ue=None,
        nb_lectures=0, nb_lectures_ue=0, qcm_done=False, anki=False,
    )

    invalidate_schedule_cache()
    assert get_course_mastery(course).score is None

    anchor_first_read("fiche-44", dt.date.today())

    assert get_course_mastery(course).score is not None
