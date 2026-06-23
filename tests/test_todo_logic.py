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
from frontend.pages.todo import _build_course_list


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
