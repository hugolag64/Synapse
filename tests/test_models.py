"""Tests unitaires — modèles métier Synapse."""
import pytest
from datetime import datetime
from backend.core.notion.models import Cours


def _make_cours(**kwargs) -> Cours:
    defaults = dict(
        id="test-id",
        title="Pathologie cardiovasculaire",
        item_number=None,
        item_lie=None,
        college=[],
        semestre=None,
        ue_id=None,
        created_time=datetime(2024, 1, 1),
        nb_lectures=0,
    )
    defaults.update(kwargs)
    return Cours(**defaults)


class TestDisplayItemNumber:
    def test_integer_float_stripped(self):
        c = _make_cours(item_number="224.0")
        assert c.display_item_number == "224"

    def test_real_decimal_kept(self):
        c = _make_cours(item_number="224.5")
        assert c.display_item_number == "224.5"

    def test_plain_integer_unchanged(self):
        c = _make_cours(item_number="231")
        assert c.display_item_number == "231"

    def test_item_lie_uuid_not_used(self):
        # item_lie contains a Notion UUID, never an EDN number — must return ""
        c = _make_cours(item_number=None, item_lie="some-page-id")
        assert c.display_item_number == ""

    def test_empty_when_both_none(self):
        c = _make_cours(item_number=None, item_lie=None)
        assert c.display_item_number == ""

    def test_whitespace_treated_as_empty(self):
        c = _make_cours(item_number="   ")
        assert c.display_item_number == ""


class TestCoursDefaults:
    def test_nb_lectures_default_zero(self):
        c = _make_cours()
        assert c.nb_lectures == 0

    def test_rappel_done_default_false(self):
        c = _make_cours()
        assert c.rappel_done is False

    def test_anki_default_false(self):
        c = _make_cours()
        assert c.anki is False

    def test_course_status_default(self):
        c = _make_cours()
        assert c.course_status == "À lire"
