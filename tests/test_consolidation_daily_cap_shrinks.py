"""Reporter (ou ignorer) un item à consolider doit réduire la charge du jour.

Retour d'usage : « quand je fais reporter des cours, c'est que la charge de
travail est trop importante — pas besoin d'en remettre un ». Or
`select_daily` sélectionne toujours jusqu'au plafond (6/jour) depuis le
backlog des tâches dues, recalculé à chaque rendu : reporter une tâche ne la
fait pas disparaître de la liste du jour, une autre en attente derrière le
plafond prend aussitôt sa place — la charge affichée ne baisse jamais tant
que le backlog dépasse le plafond, ce qui est le cas courant (113 tâches
dues contre 6 affichées, mesuré sur la base réelle).

`done` ne doit PAS avoir ce comportement : terminer une tâche est un progrès,
on veut bien qu'une autre prenne sa place pour continuer à travailler.
"""
import datetime

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import backend.core.knowledge.store as ks
    import backend.core.reviews.local_store as ls

    test_db = tmp_path / "test.db"
    monkeypatch.setattr(ls, "DB_PATH", test_db)
    monkeypatch.setattr(ls, "_DB", None)
    ls.init_db()
    ks.init_knowledge_tables()
    yield
    if ls._DB is not None:
        ls._DB.close()
    monkeypatch.setattr(ls, "_DB", None)


import backend.core.reviews.local_store as ls  # noqa: E402

_TODAY = datetime.date(2026, 8, 21)


def _postpone(n: int) -> None:
    for i in range(n):
        ls.postpone(
            task_id=f"course-{i}_college_consolidation_{_TODAY.isoformat()}",
            course_id=f"course-{i}", context="college", review_type="consolidation",
            theoretical_due_date=_TODAY, postponed_to=_TODAY + datetime.timedelta(days=3),
        )


def _ignore(n: int, offset: int = 0) -> None:
    for i in range(offset, offset + n):
        ls.ignore(
            task_id=f"course-{i}_college_consolidation_{_TODAY.isoformat()}",
            course_id=f"course-{i}", context="college", review_type="consolidation",
            theoretical_due_date=_TODAY,
        )


def test_no_dismissal_today_leaves_the_cap_untouched():
    assert ls.count_consolidation_dismissed_today("college", _TODAY) == 0


def test_each_postpone_today_counts_once():
    _postpone(3)
    assert ls.count_consolidation_dismissed_today("college", _TODAY) == 3


def test_ignore_counts_the_same_as_postpone():
    _ignore(2)
    assert ls.count_consolidation_dismissed_today("college", _TODAY) == 2


def test_dismissals_in_a_different_context_do_not_count():
    ls.postpone(
        task_id=f"course-x_ue_consolidation_{_TODAY.isoformat()}",
        course_id="course-x", context="ue", review_type="consolidation",
        theoretical_due_date=_TODAY, postponed_to=_TODAY + datetime.timedelta(days=3),
    )
    assert ls.count_consolidation_dismissed_today("college", _TODAY) == 0


def test_dismissals_from_a_previous_day_do_not_count():
    # postpone() horodate toujours updated_at avec l'heure réelle : pour
    # simuler un report d'hier, on écrit directement la ligne.
    with ls._conn() as con:
        con.execute(
            "INSERT INTO review_history (task_id, course_id, context, review_type, "
            "theoretical_due_date, effective_due_date, status, postponed_to, "
            "postponed_count, created_at, updated_at) "
            "VALUES ('course-old_college_consolidation_2026-08-01', 'course-old', "
            "'college', 'consolidation', '2026-08-01', '2026-08-04', 'postponed', "
            "'2026-08-04', 1, '2026-08-20T09:00:00', '2026-08-20T09:00:00')"
        )
    assert ls.count_consolidation_dismissed_today("college", _TODAY) == 0


def test_done_tasks_are_not_counted_as_dismissed():
    """Terminer une tâche fait légitimement place à la suivante — ce n'est
    pas un signal de surcharge, contrairement à reporter ou ignorer."""
    ls.mark_consolidation_done(
        course_id="course-1", context="college", theoretical_due_date=_TODAY,
    )
    assert ls.count_consolidation_dismissed_today("college", _TODAY) == 0


def test_plan_consolidation_shrinks_the_daily_cap_after_a_postpone(monkeypatch):
    """La sélection du jour doit refléter les reports déjà faits aujourd'hui,
    pas repartir d'un plafond plein à chaque rebuild."""
    from types import SimpleNamespace

    from backend.core.planning.service import planning_service
    from backend.core.reviews import consolidation
    from backend.state.store import data_store

    monkeypatch.setattr(data_store, "preferences", {})

    def _due(*_args, **_kwargs):
        # Un collège distinct par tâche : seul le plafond total (max_items)
        # doit jouer ici, pas le plafond par collège. Reflète les reports déjà
        # faits, comme le fait la vraie get_due_consolidation_tasks (un item
        # reporté a une due_date future, donc hors backlog du jour).
        with ls._conn() as con:
            dismissed = {
                row["course_id"] for row in con.execute(
                    "SELECT course_id FROM review_history WHERE status IN ('postponed', 'ignored')"
                ).fetchall()
            }
        return [
            SimpleNamespace(
                course_id=f"course-{i}", days_overdue=5, semestre=None,
                mastery_level="à consolider", college=[f"college-{i}"], due_date=_TODAY,
            )
            for i in range(20) if f"course-{i}" not in dismissed
        ]

    monkeypatch.setattr(consolidation, "get_due_consolidation_tasks", _due)
    monkeypatch.setattr(consolidation, "daily_caps", lambda **_: (6, 6))

    selected_before, _ = planning_service.plan_consolidation(today=_TODAY)
    assert len(selected_before) == 6

    _postpone(2)

    selected_after, _ = planning_service.plan_consolidation(today=_TODAY)
    assert len(selected_after) == 4
