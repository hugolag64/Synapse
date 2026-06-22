"""Tests unitaires — génération des révisions (ReviewService)."""
import pytest
import datetime
from unittest.mock import patch
from backend.core.reviews.service import ReviewService, REVIEW_OFFSETS
from backend.core.reviews.local_store import make_task_id
from backend.core.reviews.models import ReviewTask
from backend.core.notion.models import Cours


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_cours(days_since_lecture: int, nb_lectures: int = 1, **kwargs) -> Cours:
    today = datetime.date.today()
    lecture_date = today - datetime.timedelta(days=days_since_lecture)
    defaults = dict(
        id="c1",
        title="Cardio",
        item_number="224",
        college=["Cardiologie"],
        semestre="S1",
        ue_id=None,
        created_time=datetime.datetime(2024, 1, 1),
        url_pdf="file:///fake.pdf",
        url_pdf_ue="file:///fake.pdf",
        agregation_fiche_edn=None,
        nb_lectures=nb_lectures,
        nb_lectures_ue=0,
        date_1ere_lecture=lecture_date,
        date_1ere_lecture_ue=None,
        rappel_done=False,
        rappel_ue_done=False,
        anki=False,
        qcm_done=False,
        course_status="À lire",
    )
    defaults.update(kwargs)
    return Cours(**defaults)


def _fake_row(status="done", postponed_to=None, postponed_count=0) -> dict:
    """
    Simule un sqlite3.Row avec accès par clé.
    L'API SQLite utilise row["status"], row["postponed_to"], row["postponed_count"].
    Un dict suffit pour les tests.
    """
    return {
        "status": status,
        "postponed_to": postponed_to,
        "postponed_count": postponed_count,
    }


# ── Tests génération principale ───────────────────────────────────────────────

class TestReviewGeneration:
    def setup_method(self):
        self.svc = ReviewService()

    def _generate(self, cours_list, history=None):
        """
        Patch data_store au niveau du module store (import local dans service.py).
        Passe history directement — plus besoin de SQLite dans les tests.
        """
        with patch("backend.state.store.data_store") as mock_store:
            mock_store.cours = cours_list
            return self.svc.generate_reviews(history=history or {})

    def test_no_tasks_without_date_1ere_lecture(self):
        c = _make_cours(days_since_lecture=10, date_1ere_lecture=None)
        tasks = self._generate([c])
        assert tasks == []

    def test_j3_task_generated_after_3_days(self):
        tasks = self._generate([_make_cours(days_since_lecture=3)])
        types = [t.review_type for t in tasks]
        assert "J3" in types

    def test_j7_j14_j30_generated_after_30_days(self):
        tasks = self._generate([_make_cours(days_since_lecture=32)])
        types = {t.review_type for t in tasks}
        assert {"J7", "J14", "J30"}.issubset(types)

    def test_j30_overdue_after_32_days(self):
        tasks = self._generate([_make_cours(days_since_lecture=32)])
        j30 = next((t for t in tasks if t.review_type == "J30"), None)
        assert j30 is not None
        assert j30.days_overdue >= 2

    def test_done_task_excluded_via_history(self):
        c = _make_cours(days_since_lecture=7)
        theoretical = c.date_1ere_lecture + datetime.timedelta(days=7)
        task_id = make_task_id(c.id, "college", "J7", theoretical)
        history = {task_id: _fake_row(status="done")}
        tasks = self._generate([c], history=history)
        assert not any(t.id == task_id for t in tasks)

    def test_ignored_task_excluded_via_history(self):
        c = _make_cours(days_since_lecture=14)
        theoretical = c.date_1ere_lecture + datetime.timedelta(days=14)
        task_id = make_task_id(c.id, "college", "J14", theoretical)
        history = {task_id: _fake_row(status="ignored")}
        tasks = self._generate([c], history=history)
        assert not any(t.id == task_id for t in tasks)

    def test_postponed_shifts_effective_date(self):
        c = _make_cours(days_since_lecture=7)
        theoretical = c.date_1ere_lecture + datetime.timedelta(days=7)
        task_id = make_task_id(c.id, "college", "J7", theoretical)
        new_date = datetime.date.today() + datetime.timedelta(days=5)
        history = {
            task_id: _fake_row(
                status="postponed",
                postponed_to=new_date.isoformat(),
                postponed_count=1,
            )
        }
        tasks = self._generate([c], history=history)
        t = next((t for t in tasks if t.id == task_id), None)
        assert t is not None
        assert t.due_date == new_date
        assert t.postponed_count == 1

    def test_theoretical_date_unchanged_after_postpone(self):
        c = _make_cours(days_since_lecture=7)
        theoretical = c.date_1ere_lecture + datetime.timedelta(days=7)
        task_id = make_task_id(c.id, "college", "J7", theoretical)
        new_date = datetime.date.today() + datetime.timedelta(days=5)
        history = {
            task_id: _fake_row(status="postponed", postponed_to=new_date.isoformat(), postponed_count=2)
        }
        tasks = self._generate([c], history=history)
        t = next((t for t in tasks if t.id == task_id), None)
        assert t is not None
        assert t.theoretical_due_date == theoretical  # date Notion inchangée

    def test_tasks_sorted_by_priority_desc(self):
        tasks = self._generate([_make_cours(days_since_lecture=32)])
        scores = [t.priority_score for t in tasks]
        assert scores == sorted(scores, reverse=True)

    def test_future_horizon_includes_j3(self):
        # Cours lu hier → J3 dans 2 jours → dans l'horizon (30j par défaut)
        tasks = self._generate([_make_cours(days_since_lecture=1)])
        assert any(t.review_type == "J3" for t in tasks)

    def test_far_future_excluded(self):
        # Cours lu aujourd'hui → J30 dans 30 jours → pile dans l'horizon
        # J30 dans 31 jours serait exclu (> FUTURE_HORIZON_DAYS=30)
        tasks = self._generate([_make_cours(days_since_lecture=0)])
        j30 = next((t for t in tasks if t.review_type == "J30"), None)
        # J30 = today + 30 → days_overdue = -30 → exactement dans l'horizon
        assert j30 is not None

    def test_context_college_by_default(self):
        tasks = self._generate([_make_cours(days_since_lecture=7)])
        assert all(t.context == "college" for t in tasks)

    def test_ue_context_uses_date_1ere_lecture_ue(self):
        today = datetime.date.today()
        c = _make_cours(
            days_since_lecture=7,
            date_1ere_lecture_ue=today - datetime.timedelta(days=7),
        )
        with patch("backend.state.store.data_store") as mock_store:
            mock_store.cours = [c]
            tasks = self.svc.generate_reviews(context="ue", history={})
        assert any(t.review_type == "J7" for t in tasks)

    def test_no_ue_tasks_without_date_1ere_lecture_ue(self):
        c = _make_cours(days_since_lecture=7)  # date_1ere_lecture_ue=None par défaut
        with patch("backend.state.store.data_store") as mock_store:
            mock_store.cours = [c]
            tasks = self.svc.generate_reviews(context="ue", history={})
        assert tasks == []


# ── Tests tâches bonus ────────────────────────────────────────────────────────

class TestBonusTasks:
    def setup_method(self):
        self.svc = ReviewService()

    def _bonus(self, cours_list, history=None):
        with patch("backend.state.store.data_store") as mock_store:
            mock_store.cours = cours_list
            return self.svc.get_bonus_tasks(history=history or {})

    def test_cours_jamais_lu_in_bonus(self):
        c = _make_cours(days_since_lecture=0, nb_lectures=0)
        bonus = self._bonus([c])
        assert any(t.course_id == c.id for t in bonus)

    def test_cours_avec_lectures_non_nul_peut_etre_en_bonus(self):
        # nb_lectures=1 mais pas de fiche EDN → toujours candidat bonus
        c = _make_cours(days_since_lecture=10, nb_lectures=1, agregation_fiche_edn=None)
        bonus = self._bonus([c])
        assert any(t.course_id == c.id for t in bonus)

    def test_cours_complet_not_in_bonus(self):
        # nb_lectures > 0 ET fiche EDN présente → plus de raison bonus
        c = _make_cours(
            days_since_lecture=10,
            nb_lectures=3,
            agregation_fiche_edn="https://notion.so/abc",
            qcm_done=True,
        )
        bonus = self._bonus([c])
        assert not any(t.course_id == c.id for t in bonus)

    def test_bonus_capped_at_12(self):
        cours = [_make_cours(days_since_lecture=0, nb_lectures=0, id=f"c{i}") for i in range(20)]
        bonus = self._bonus(cours)
        assert len(bonus) <= 12

    def test_bonus_done_excluded_via_history(self):
        c = _make_cours(days_since_lecture=0, nb_lectures=0)
        today = datetime.date.today()
        task_id = make_task_id(c.id, "college", "bonus", today)
        history = {task_id: _fake_row(status="done")}
        bonus = self._bonus([c], history=history)
        assert not any(t.course_id == c.id for t in bonus)

    def test_bonus_sorted_by_priority_desc(self):
        cours = [_make_cours(days_since_lecture=0, nb_lectures=0, id=f"c{i}") for i in range(5)]
        bonus = self._bonus(cours)
        scores = [t.priority_score for t in bonus]
        assert scores == sorted(scores, reverse=True)


# ── Tests filtres urgents/prévus ──────────────────────────────────────────────

class TestReviewFilters:
    def setup_method(self):
        self.svc = ReviewService()
        self.today = datetime.date.today()

    def _task(self, due_offset: int, review_type="J7") -> ReviewTask:
        due = self.today + datetime.timedelta(days=due_offset)
        return ReviewTask(
            id=f"fake_{due_offset}",
            course_id="c1",
            course_title="Test",
            item_number="1",
            college=["Col"],
            context="college",
            url_pdf=None,
            url_pdf_ue=None,
            agregation_fiche_edn=None,
            theoretical_due_date=due,
            due_date=due,
            review_type=review_type,
            priority_score=10.0,
            status="todo",
            nb_lectures=1,
            anki=False,
            qcm_done=False,
            course_status="À lire",
            days_overdue=max(-due_offset, 0),
        )

    def test_get_urgent_tasks_returns_overdue(self):
        tasks = [self._task(-2), self._task(0), self._task(3)]
        urgent = self.svc.get_urgent_tasks(tasks)
        assert len(urgent) == 1
        assert urgent[0].due_date < self.today

    def test_get_today_tasks(self):
        tasks = [self._task(-1), self._task(0), self._task(1)]
        today_tasks = self.svc.get_today_tasks(tasks)
        assert len(today_tasks) == 1
        assert today_tasks[0].due_date == self.today

    def test_get_upcoming_tasks_default_7_days(self):
        tasks = [self._task(0), self._task(3), self._task(7), self._task(8)]
        upcoming = self.svc.get_upcoming_tasks(tasks)
        assert len(upcoming) == 2  # J+3 et J+7, pas J+0 ni J+8
