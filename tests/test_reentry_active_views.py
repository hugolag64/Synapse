from pathlib import Path


ACTIVE_REVIEW_CALLERS = (
    "frontend/pages/dashboard/_cockpit_today.py",
    "frontend/pages/dashboard/_monday.py",
    "frontend/pages/todo_cockpit.py",
    "frontend/pages/planning_cockpit.py",
    "frontend/pages/colleges_cockpit.py",
    "frontend/pages/items.py",
    "frontend/cockpit_shell.py",
    "backend/features/daily_routine.py",
)


def test_active_views_request_the_central_reentry_filter():
    """Deux formes acceptées : le raccourci `active_only=True`, ou le filtre
    central appliqué explicitement — ce que font Items et Collèges pour pouvoir
    annoncer le nombre de révisions masquées au lieu de les escamoter."""
    for path in ACTIVE_REVIEW_CALLERS:
        source = Path(path).read_text(encoding="utf-8")
        assert (
            "active_only=True" in source
            or "filter_active_review_tasks(" in source
        ), path


def test_views_hiding_pre_reentry_reviews_say_how_many_they_hide():
    for path in ("frontend/pages/colleges_cockpit.py", "frontend/pages/items.py"):
        source = Path(path).read_text(encoding="utf-8")
        assert "hidden_tasks" in source, path
        assert "masquée(s)" in source, path


def test_item_detail_keeps_full_review_generation_for_manual_access():
    source = Path("frontend/pages/course_detail_cockpit.py").read_text(encoding="utf-8")
    assert "active_only=True" not in source


def test_consolidation_tasks_are_not_hidden_by_the_reentry_boundary():
    """`get_due_consolidation_tasks` amorce (bootstrap) sa propre due_date à la
    volée : elle peut retomber avant la date de reprise dès la création de la
    tâche, sans rapport avec du passif accumulé pendant une pause. Appliquer le
    filtre de reprise ici la cachait des vues liste alors que la fiche détail
    (`get_due_consolidation_task_for_course`) l'affichait — la même tâche
    existait ou non selon la vue."""
    source = Path("backend/core/reviews/consolidation.py").read_text(encoding="utf-8")
    assert "filter_active_review_tasks" not in source
    assert "get_study_resume_date" not in source


def test_generate_reviews_hides_completed_reviews_even_without_an_explicit_history():
    """`generate_reviews()` retombait sur un historique vide : les vues qui ne
    passaient pas `history=` (Collèges, fiche item) reproposaient des révisions
    déjà validées."""
    from pathlib import Path

    source = Path("backend/core/reviews/service.py").read_text(encoding="utf-8")

    assert "history      = history      or {}" not in source
    assert "history if history is not None else get_all_history()" in source
