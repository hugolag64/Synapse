"""Un item EDN peut avoir plusieurs fiches Notion, une par collège.

Mesuré sur les données réelles : 162 items sur 365 ont 2 à 4 fiches, et TOUS
ont leur historique éclaté entre elles. Réviser depuis la fiche Chirurgie
digestive rend la révision invisible depuis la fiche Orthopédie du même item,
et la maîtrise existe en autant d'exemplaires partiels.

Ces fonctions rassemblent les fiches d'un item pour que l'application les
traite comme une seule, sans rien déplacer en base ni dans Notion.
"""

from types import SimpleNamespace

from backend.core.knowledge.course_aliases import (
    canonical_course,
    colleges_of_item,
    group_courses_by_item,
)


def _course(cid, item, colleges, title="Cours", created=1):
    return SimpleNamespace(
        id=cid, item_number=item, college=list(colleges), title=title, created_time=created
    )


def test_courses_are_grouped_by_item_number():
    courses = [
        _course("a", "357", ["Orthopédie - Traumatologie 🦴"]),
        _course("b", "357", ["Chirurgie digestive 🧵"]),
        _course("c", "230", ["Cardiovasculaire ❤️"]),
    ]

    groups = group_courses_by_item(courses)

    assert sorted(groups) == ["230", "357"]
    assert {c.id for c in groups["357"]} == {"a", "b"}


def test_courses_without_item_are_left_out_of_any_group():
    """Avant l'externat, les cours n'étaient pas organisés par collège ni par
    item : ils n'ont rien à faire dans un regroupement par item."""
    groups = group_courses_by_item([_course("a", "", ["UE 3"]), _course("b", None, [])])

    assert groups == {}


def test_an_item_exposes_the_union_of_its_colleges():
    courses = [
        _course("a", "357", ["Orthopédie - Traumatologie 🦴", "Chirurgie digestive 🧵"]),
        _course("b", "357", ["Anesthésie-Réanimation 💉"]),
        _course("c", "357", ["Chirurgie digestive 🧵"]),
    ]

    colleges = colleges_of_item(courses)

    assert colleges == [
        "Orthopédie - Traumatologie 🦴",
        "Chirurgie digestive 🧵",
        "Anesthésie-Réanimation 💉",
    ]


def test_the_canonical_fiche_is_the_one_in_the_referential_college():
    """Item 230 = Douleur thoracique aiguë, collège Cardiovasculaire."""
    ortho = _course("a", "230", ["Orthopédie - Traumatologie 🦴"])
    cardio = _course("b", "230", ["Cardiovasculaire ❤️"])

    assert canonical_course([ortho, cardio]) is cardio


def test_the_canonical_fiche_falls_back_on_the_oldest_when_no_college_matches():
    first = _course("a", "230", ["Orthopédie - Traumatologie 🦴"], created=1)
    second = _course("b", "230", ["Pédiatrie 🚼"], created=2)

    assert canonical_course([second, first]) is first


def test_canonical_of_a_single_fiche_is_itself():
    only = _course("a", "230", [])

    assert canonical_course([only]) is only


def test_a_college_lists_each_item_once():
    """Deux fiches du même item peuvent porter le même collège : la liste du
    collège ne doit montrer l'item qu'une fois, sur sa fiche de référence.

    Ici les deux fiches sont rattachées au collège du référentiel (item 357 =
    Chirurgie digestive) : le départage revient à l'ordre d'entrée, stable.
    """
    from backend.core.knowledge.course_aliases import dedupe_by_item

    ortho = _course("a", "357", ["Orthopédie - Traumatologie 🦴", "Chirurgie digestive 🧵"])
    chir = _course("b", "357", ["Chirurgie digestive 🧵"])
    autre = _course("c", "358", ["Chirurgie digestive 🧵"])

    kept = dedupe_by_item([ortho, chir, autre])

    assert [c.id for c in kept] == ["a", "c"]


def test_courses_without_item_are_all_kept():
    from backend.core.knowledge.course_aliases import dedupe_by_item

    a = _course("a", "", ["UE 3"])
    b = _course("b", None, ["UE 3"])

    assert [c.id for c in dedupe_by_item([a, b])] == ["a", "b"]


def test_dedupe_preserves_the_incoming_order():
    from backend.core.knowledge.course_aliases import dedupe_by_item

    first = _course("a", "230", ["Cardiovasculaire ❤️"])
    second = _course("b", "231", ["Cardiovasculaire ❤️"])

    assert [c.id for c in dedupe_by_item([first, second])] == ["a", "b"]


def test_referential_college_is_stable_whichever_fiche_is_opened():
    """Le fil d'Ariane prenait le premier collège Notion : il changeait selon la
    fiche ouverte alors que l'item est le même. Le référentiel donne un
    rattachement stable."""
    from backend.core.knowledge.course_aliases import referential_college

    depuis_ortho = _course("a", "230", ["Orthopédie - Traumatologie 🦴"])
    depuis_cardio = _course("b", "230", ["Cardiovasculaire ❤️"])

    assert referential_college(depuis_ortho) == referential_college(depuis_cardio)
    assert "Cardiovasculaire" in referential_college(depuis_ortho)


def test_referential_college_is_empty_for_an_unknown_item():
    from backend.core.knowledge.course_aliases import referential_college

    assert referential_college(_course("a", "9999", ["Pédiatrie 🚼"])) == ""
    assert referential_college(_course("b", "", ["Pédiatrie 🚼"])) == ""


def test_item_page_breadcrumb_uses_the_referential_college():
    from pathlib import Path

    source = Path("frontend/pages/course_detail_cockpit.py").read_text(encoding="utf-8")

    assert "referential_college(course)" in source
    assert 'college = (course.college or [""])[0] if course.college else ""' not in source
