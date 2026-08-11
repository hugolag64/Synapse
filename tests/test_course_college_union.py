"""Un item peut relever de deux collèges — le modèle doit le représenter.

« Tuberculose de l'adulte et de l'enfant », « Diarrhées infectieuses de l'adulte
et de l'enfant », « Coqueluche »… sont enseignés en Pédiatrie *et* en
Infectiologie. Notion n'en portait qu'un, le référentiel UNESS l'autre, et
l'écart était compté comme une contradiction sur 289 cours. C'est en réalité une
double appartenance légitime : la liste des collèges d'un cours est l'union des
deux sources.
"""

from datetime import datetime

import pytest

from backend.core.notion.models import Cours


def _course(**overrides):
    values = dict(
        id="c1",
        title="Tuberculose de l'adulte et de l'enfant",
        item_number="159",
        college=["Pédiatrie 🚼"],
        created_time=datetime(2026, 1, 1),
    )
    values.update(overrides)
    return Cours(**values)


def test_course_gains_the_referential_college():
    course = _course()

    assert "Pédiatrie 🚼" in course.college
    assert any("Infectiologie" in c for c in course.college)


def test_the_notion_college_always_comes_first():
    """L'organisation de l'utilisateur reste l'entrée principale de la liste."""
    course = _course()

    assert course.college[0] == "Pédiatrie 🚼"


def test_no_duplicate_when_both_sources_agree():
    course = _course(item_number="230", college=["Cardiovasculaire ❤️"])

    assert course.college == ["Cardiovasculaire ❤️"]


def test_a_course_without_item_keeps_its_colleges_untouched():
    course = _course(item_number="", college=["Pédiatrie 🚼"])

    assert course.college == ["Pédiatrie 🚼"]


def test_a_course_without_college_still_gets_the_referential_one():
    course = _course(college=[])

    assert any("Infectiologie" in c for c in course.college)


def test_an_unknown_item_does_not_invent_a_college():
    course = _course(item_number="9999", college=["Pédiatrie 🚼"])

    assert course.college == ["Pédiatrie 🚼"]


@pytest.mark.parametrize("bad", ["", "abc", None])
def test_a_malformed_item_number_is_survived(bad):
    course = _course(item_number=bad, college=["Pédiatrie 🚼"])

    assert course.college == ["Pédiatrie 🚼"]
