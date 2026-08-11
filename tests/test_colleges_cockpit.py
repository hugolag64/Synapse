from types import SimpleNamespace




def test_started_counts_every_form_of_real_activity():
    """« Progression » ne comptait que la date de première lecture : 8 cours sur
    707, alors que 250 révisions avaient été faites — dont 80 % par des chemins
    (consolidation, bonus, annales) qui ne renseignent pas ce champ. L'indicateur
    suggérait donc une inactivité qui n'existait pas."""
    from frontend.pages.colleges_cockpit import count_started

    courses = [
        SimpleNamespace(id="c1", date_1ere_lecture="2026-03-01"),
        SimpleNamespace(id="c2", date_1ere_lecture=None),
        SimpleNamespace(id="c3", date_1ere_lecture=None),
        SimpleNamespace(id="c4", date_1ere_lecture=None),
    ]

    assert count_started(courses, active_course_ids={"c2", "c3"}) == 3


def test_started_does_not_double_count_a_course_with_both_signals():
    from frontend.pages.colleges_cockpit import count_started

    courses = [SimpleNamespace(id="c1", date_1ere_lecture="2026-03-01")]

    assert count_started(courses, active_course_ids={"c1"}) == 1


def test_started_is_zero_without_any_signal():
    from frontend.pages.colleges_cockpit import count_started

    courses = [SimpleNamespace(id="c1", date_1ere_lecture=None)]

    assert count_started(courses, active_course_ids=set()) == 0
