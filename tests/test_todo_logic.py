"""Tests unitaires — logique pure de la page To Do."""
import pytest
from unittest.mock import MagicMock


class _MockCourse:
    def __init__(self, id, title, college=True, item_number=None, nb_lectures=0):
        self.id          = id
        self.title       = title
        self.college     = college
        self.item_number = item_number
        self.nb_lectures = nb_lectures


@pytest.fixture
def courses():
    return [
        _MockCourse('c1', 'Insuffisance cardiaque', item_number='232'),
        _MockCourse('c2', 'Diabète', item_number='245'),
        _MockCourse('c3', 'Non collège', college=False),
    ]


# Import after fixture to avoid NiceGUI import errors at module level
from frontend.pages.todo import _build_course_list, _compute_ajoute_progress


class TestBuildCourseList:
    def test_empty_inputs(self, courses):
        assert _build_course_list([], [], courses) == []

    def test_none_inputs(self, courses):
        assert _build_course_list(None, None, courses) == []

    def test_gcal_event_matched(self, courses):
        events = [{'summary': 'Collège — Insuffisance cardiaque'}]
        result = _build_course_list(events, [], courses)
        assert len(result) == 1
        assert result[0]['type'] == 'gcal'
        assert result[0]['course'].id == 'c1'

    def test_gcal_revision_manuelle_matched(self, courses):
        events = [{'summary': 'Révision Manuelle Diabète'}]
        result = _build_course_list(events, [], courses)
        assert len(result) == 1
        assert result[0]['course'].id == 'c2'

    def test_manual_notion_matched(self, courses):
        result = _build_course_list([], ['Diabète'], courses)
        assert len(result) == 1
        assert result[0]['type'] == 'notion_manual'
        assert result[0]['course'].id == 'c2'

    def test_no_duplicate_gcal_and_manual(self, courses):
        events = [{'summary': 'Collège — Insuffisance cardiaque'}]
        result = _build_course_list(events, ['Insuffisance cardiaque'], courses)
        assert len(result) == 1  # Pas de doublon

    def test_unmatched_event_ignored(self, courses):
        events = [{'summary': 'Cours magistral de cardiologie'}]
        result = _build_course_list(events, [], courses)
        assert result == []

    def test_multiple_sources(self, courses):
        events = [{'summary': 'Collège — Insuffisance cardiaque'}]
        result = _build_course_list(events, ['Diabète'], courses)
        assert len(result) == 2
        assert result[0]['type'] == 'gcal'
        assert result[1]['type'] == 'notion_manual'


class TestComputeAjouteProgress:
    def test_empty(self):
        assert _compute_ajoute_progress([], [], {}) == (0, 0)

    def test_all_courses_reviewed(self, courses):
        items = [{'course': courses[0]}, {'course': courses[1]}]
        reviewed = [courses[0].title, courses[1].title]
        assert _compute_ajoute_progress(items, reviewed, {}) == (2, 2)

    def test_partial_courses(self, courses):
        items = [{'course': courses[0]}, {'course': courses[1]}]
        reviewed = [courses[0].title]
        assert _compute_ajoute_progress(items, reviewed, {}) == (2, 1)

    def test_dynamic_tasks_only(self):
        dynamic = {'b1': {'text': 'x', 'checked': True}, 'b2': {'text': 'y', 'checked': False}}
        assert _compute_ajoute_progress([], [], dynamic) == (2, 1)

    def test_mixed_courses_and_dynamic(self, courses):
        items = [{'course': courses[0]}]
        reviewed = [courses[0].title]
        dynamic = {'b1': {'text': 'x', 'checked': False}}
        assert _compute_ajoute_progress(items, reviewed, dynamic) == (2, 1)


from frontend.pages.todo import _DaySummary


class TestDaySummary:
    def test_pct_zero_total(self):
        assert _DaySummary().pct == 0.0

    def test_pct_routine_only(self):
        s = _DaySummary(routine_total=4, routine_done=2)
        assert s.pct == 0.5

    def test_pct_full(self):
        s = _DaySummary(routine_total=2, routine_done=2, ajoute_total=2, ajoute_done=2, ajoute_loaded=True)
        assert s.pct == 1.0

    def test_pct_partial_with_ajoute(self):
        s = _DaySummary(routine_total=4, routine_done=4, ajoute_total=4, ajoute_done=1, ajoute_loaded=True)
        assert s.pct == pytest.approx(0.625)

    def test_total_and_done(self):
        s = _DaySummary(routine_total=3, routine_done=1, ajoute_total=2, ajoute_done=2)
        assert s.total == 5
        assert s.done == 3


import datetime
from frontend.pages.todo import _compute_carryover, _week_dates


class TestComputeCarryover:
    def test_empty(self):
        assert _compute_carryover([], []) == []

    def test_all_done(self):
        assert _compute_carryover(['A', 'B'], ['A', 'B']) == []

    def test_none_done(self):
        assert _compute_carryover(['A', 'B'], []) == ['A', 'B']

    def test_partial(self):
        assert _compute_carryover(['A', 'B', 'C'], ['B']) == ['A', 'C']


class TestWeekDates:
    def test_length(self):
        assert len(_week_dates(datetime.date(2026, 7, 3))) == 7

    def test_centered(self):
        result = _week_dates(datetime.date(2026, 7, 3))
        assert result[3] == datetime.date(2026, 7, 3)
        assert result[0] == datetime.date(2026, 6, 30)
        assert result[6] == datetime.date(2026, 7, 6)
