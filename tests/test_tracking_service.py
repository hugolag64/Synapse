"""
Tests du CourseTrackingService.

Toutes les fonctions testées ici sont PURES (aucun I/O, aucun mock nécessaire).
"""
import datetime
import pytest
from types import SimpleNamespace

from backend.core.tracking.service import (
    CourseTrackingService,
    TrackingStatus,
    REVIEW_INTERVALS,
    tracking_service,
)
from backend.config.settings import NOTION_PROPS as P


# ── Fixtures ──────────────────────────────────────────────────────────────────

TODAY = datetime.date(2026, 5, 24)
DATE_J0 = datetime.date(2026, 5, 1)  # date de référence pour les tests


def _course(
    *,
    date_1ere_lecture=None,
    lecture_j3_college=None,
    lecture_j7_college=None,
    lecture_j14_college=None,
    lecture_j30_college=None,
    nb_lectures=0,
    date_1ere_lecture_ue=None,
    lecture_j3_ue=None,
    lecture_j7_ue=None,
    lecture_j14_ue=None,
    lecture_j30_ue=None,
    nb_lectures_ue=0,
):
    """Fabrique un objet cours minimal pour les tests."""
    return SimpleNamespace(
        date_1ere_lecture=date_1ere_lecture,
        lecture_j3_college=lecture_j3_college,
        lecture_j7_college=lecture_j7_college,
        lecture_j14_college=lecture_j14_college,
        lecture_j30_college=lecture_j30_college,
        nb_lectures=nb_lectures,
        date_1ere_lecture_ue=date_1ere_lecture_ue,
        lecture_j3_ue=lecture_j3_ue,
        lecture_j7_ue=lecture_j7_ue,
        lecture_j14_ue=lecture_j14_ue,
        lecture_j30_ue=lecture_j30_ue,
        nb_lectures_ue=nb_lectures_ue,
    )


svc = CourseTrackingService()


# ── compute_review_dates ──────────────────────────────────────────────────────

class TestComputeReviewDates:
    def test_all_labels_present(self):
        result = svc.compute_review_dates(DATE_J0)
        assert set(result.keys()) == {"J3", "J7", "J14", "J30"}

    def test_j3_correct(self):
        result = svc.compute_review_dates(DATE_J0)
        assert result["J3"] == DATE_J0 + datetime.timedelta(days=3)

    def test_j7_correct(self):
        result = svc.compute_review_dates(DATE_J0)
        assert result["J7"] == DATE_J0 + datetime.timedelta(days=7)

    def test_j14_correct(self):
        result = svc.compute_review_dates(DATE_J0)
        assert result["J14"] == DATE_J0 + datetime.timedelta(days=14)

    def test_j30_correct(self):
        result = svc.compute_review_dates(DATE_J0)
        assert result["J30"] == DATE_J0 + datetime.timedelta(days=30)

    def test_intervals_match_constants(self):
        result = svc.compute_review_dates(DATE_J0)
        for label, days in REVIEW_INTERVALS.items():
            assert result[label] == DATE_J0 + datetime.timedelta(days=days)

    def test_end_of_month_overflow(self):
        """Doit gérer les débordements de mois sans erreur."""
        d = datetime.date(2026, 1, 25)
        result = svc.compute_review_dates(d)
        assert result["J7"] == datetime.date(2026, 2, 1)
        assert result["J30"] == datetime.date(2026, 2, 24)


# ── build_tracking_payload — college ─────────────────────────────────────────

class TestBuildTrackingPayloadCollege:
    def setup_method(self):
        self.payload = svc.build_tracking_payload("college", DATE_J0)

    def test_contains_rappel(self):
        assert P.RAPPEL_COLLEGE in self.payload
        assert self.payload[P.RAPPEL_COLLEGE] == {"checkbox": True}

    def test_contains_date_lecture(self):
        assert P.DATE_LECTURE_COLLEGE in self.payload
        assert self.payload[P.DATE_LECTURE_COLLEGE]["date"]["start"] == DATE_J0.isoformat()

    def test_contains_j3(self):
        assert P.LECTURE_J3_COLLEGE in self.payload
        expected = (DATE_J0 + datetime.timedelta(days=3)).isoformat()
        assert self.payload[P.LECTURE_J3_COLLEGE]["date"]["start"] == expected

    def test_contains_j7(self):
        assert P.LECTURE_J7_COLLEGE in self.payload
        expected = (DATE_J0 + datetime.timedelta(days=7)).isoformat()
        assert self.payload[P.LECTURE_J7_COLLEGE]["date"]["start"] == expected

    def test_contains_j14(self):
        assert P.LECTURE_J14_COLLEGE in self.payload
        expected = (DATE_J0 + datetime.timedelta(days=14)).isoformat()
        assert self.payload[P.LECTURE_J14_COLLEGE]["date"]["start"] == expected

    def test_contains_j30(self):
        assert P.LECTURE_J30_COLLEGE in self.payload
        expected = (DATE_J0 + datetime.timedelta(days=30)).isoformat()
        assert self.payload[P.LECTURE_J30_COLLEGE]["date"]["start"] == expected

    def test_no_ue_keys(self):
        assert P.RAPPEL_UE not in self.payload
        assert P.DATE_LECTURE_UE not in self.payload

    def test_exactly_six_keys(self):
        assert len(self.payload) == 6


# ── build_tracking_payload — ue ───────────────────────────────────────────────

class TestBuildTrackingPayloadUE:
    def setup_method(self):
        self.payload = svc.build_tracking_payload("ue", DATE_J0)

    def test_contains_rappel_ue(self):
        assert P.RAPPEL_UE in self.payload
        assert self.payload[P.RAPPEL_UE] == {"checkbox": True}

    def test_contains_date_lecture_ue(self):
        assert P.DATE_LECTURE_UE in self.payload
        assert self.payload[P.DATE_LECTURE_UE]["date"]["start"] == DATE_J0.isoformat()

    def test_contains_j30_ue(self):
        assert P.LECTURE_J30_UE in self.payload
        expected = (DATE_J0 + datetime.timedelta(days=30)).isoformat()
        assert self.payload[P.LECTURE_J30_UE]["date"]["start"] == expected

    def test_no_college_keys(self):
        assert P.RAPPEL_COLLEGE not in self.payload
        assert P.DATE_LECTURE_COLLEGE not in self.payload

    def test_exactly_six_keys(self):
        assert len(self.payload) == 6


# ── get_tracking_status — non démarré ────────────────────────────────────────

class TestTrackingStatusUnstarted:
    def setup_method(self):
        self.status = svc.get_tracking_status(_course(), "college")

    def test_not_started(self):
        assert self.status.is_started is False

    def test_no_first_read_date(self):
        assert self.status.first_read_date is None

    def test_no_review_dates(self):
        assert self.status.j3 is None
        assert self.status.j7 is None
        assert self.status.j14 is None
        assert self.status.j30 is None

    def test_nb_lectures_zero(self):
        assert self.status.nb_lectures == 0

    def test_not_completed(self):
        assert self.status.is_completed is False

    def test_no_next_review(self):
        assert self.status.next_review is None

    def test_no_overdue(self):
        assert self.status.overdue_reviews == []


# ── get_tracking_status — actif ───────────────────────────────────────────────

class TestTrackingStatusActive:
    def setup_method(self):
        future = datetime.date.today() + datetime.timedelta(days=5)
        course = _course(
            date_1ere_lecture=DATE_J0,
            lecture_j3_college=DATE_J0 + datetime.timedelta(days=3),
            lecture_j7_college=DATE_J0 + datetime.timedelta(days=7),
            lecture_j14_college=DATE_J0 + datetime.timedelta(days=14),
            lecture_j30_college=future,  # J30 dans le futur → pas terminé
            nb_lectures=2,
        )
        self.status = svc.get_tracking_status(course, "college")

    def test_is_started(self):
        assert self.status.is_started is True

    def test_first_read_date(self):
        assert self.status.first_read_date == DATE_J0

    def test_nb_lectures(self):
        assert self.status.nb_lectures == 2

    def test_not_completed_yet(self):
        assert self.status.is_completed is False

    def test_next_review_is_j30(self):
        result = self.status.next_review
        assert result is not None
        label, d = result
        assert label == "J30"

    def test_review_dates_dict(self):
        dates = self.status.review_dates
        assert "J3" in dates
        assert "J30" in dates


# ── get_tracking_status — cycle complet terminé ───────────────────────────────

class TestTrackingStatusCompleted:
    def setup_method(self):
        past = datetime.date.today() - datetime.timedelta(days=2)
        course = _course(
            date_1ere_lecture=DATE_J0,
            lecture_j3_college=DATE_J0 + datetime.timedelta(days=3),
            lecture_j7_college=DATE_J0 + datetime.timedelta(days=7),
            lecture_j14_college=DATE_J0 + datetime.timedelta(days=14),
            lecture_j30_college=past,  # J30 dépassé → cycle terminé
            nb_lectures=5,
        )
        self.status = svc.get_tracking_status(course, "college")

    def test_is_completed(self):
        assert self.status.is_completed is True

    def test_is_started(self):
        assert self.status.is_started is True

    def test_nb_lectures(self):
        assert self.status.nb_lectures == 5

    def test_no_future_reviews(self):
        assert self.status.next_review is None


# ── get_tracking_status — contexte UE ────────────────────────────────────────

class TestTrackingStatusUE:
    def test_ue_context_reads_ue_fields(self):
        course = _course(
            date_1ere_lecture=None,           # college non démarré
            date_1ere_lecture_ue=DATE_J0,     # ue démarré
            nb_lectures_ue=3,
        )
        status = svc.get_tracking_status(course, "ue")
        assert status.is_started is True
        assert status.first_read_date == DATE_J0
        assert status.nb_lectures == 3

    def test_college_context_ignores_ue_fields(self):
        course = _course(
            date_1ere_lecture=None,
            date_1ere_lecture_ue=DATE_J0,
        )
        status = svc.get_tracking_status(course, "college")
        assert status.is_started is False


# ── multi-cycle : redémarrage ─────────────────────────────────────────────────

class TestMultiCycle:
    def test_restart_recalculates_all_dates(self):
        """Redémarrer avec une nouvelle date → toutes les dates changent."""
        new_date = datetime.date(2026, 6, 1)
        payload1 = svc.build_tracking_payload("college", DATE_J0)
        payload2 = svc.build_tracking_payload("college", new_date)

        assert payload1[P.DATE_LECTURE_COLLEGE] != payload2[P.DATE_LECTURE_COLLEGE]
        assert payload1[P.LECTURE_J3_COLLEGE] != payload2[P.LECTURE_J3_COLLEGE]
        assert payload1[P.LECTURE_J30_COLLEGE] != payload2[P.LECTURE_J30_COLLEGE]

    def test_restart_j30_correct_for_new_date(self):
        new_date = datetime.date(2026, 6, 1)
        payload = svc.build_tracking_payload("college", new_date)
        expected = (new_date + datetime.timedelta(days=30)).isoformat()
        assert payload[P.LECTURE_J30_COLLEGE]["date"]["start"] == expected

    def test_idempotent(self):
        """Appeler deux fois avec la même date donne le même payload."""
        p1 = svc.build_tracking_payload("college", DATE_J0)
        p2 = svc.build_tracking_payload("college", DATE_J0)
        assert p1 == p2


# ── Singleton ─────────────────────────────────────────────────────────────────

def test_singleton_is_same_instance():
    from backend.core.tracking.service import tracking_service as ts1
    from backend.core.tracking.service import tracking_service as ts2
    assert ts1 is ts2


def test_singleton_produces_correct_payload():
    payload = tracking_service.build_tracking_payload("college", DATE_J0)
    assert P.RAPPEL_COLLEGE in payload
    assert len(payload) == 6
