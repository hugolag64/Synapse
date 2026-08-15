"""Rassemble les fiches Notion qui décrivent le même item EDN.

Un item est souvent saisi une fois par collège dans Notion : « Péritonite aiguë »
existe en quatre fiches (Orthopédie, Réanimation, Chirurgie digestive,
Anesthésie). Mesuré sur les données réelles : 162 items sur 365 ont de 2 à 4
fiches, et tous ont leur historique éclaté entre elles — réviser depuis l'une
rend la révision invisible depuis les autres, et la maîtrise de l'item existe en
autant d'exemplaires partiels.

Ce module n'écrit rien : il donne aux lectures de quoi traiter ces fiches comme
un seul item. Notion garde ses doublons, qui restent l'entrée par collège.
"""

from __future__ import annotations

from typing import Iterable, Sequence, TypeVar

from backend.core.qcm.items_mapping import item_colleges

Course = TypeVar("Course")


def normalized_item(course) -> str:
    """Numéro d'item sous forme canonique, ou '' si le cours n'en a pas."""
    raw = str(getattr(course, "item_number", "") or "").strip()
    if not raw:
        return ""
    try:
        return str(int(float(raw)))
    except (TypeError, ValueError):
        return ""


def group_courses_by_item(courses: Iterable) -> dict[str, list]:
    """Fiches regroupées par item. Les cours sans item sont écartés.

    Avant l'externat les cours n'étaient organisés ni par collège ni par item :
    leur absence de regroupement est normale, pas une anomalie.
    """
    groups: dict[str, list] = {}
    for course in courses:
        item = normalized_item(course)
        if item:
            groups.setdefault(item, []).append(course)
    return groups


def colleges_of_item(courses: Sequence) -> list[str]:
    """Union ordonnée des collèges de toutes les fiches d'un item."""
    seen: list[str] = []
    for course in courses:
        for college in getattr(course, "college", None) or []:
            label = str(college).strip()
            if label and label not in seen:
                seen.append(label)
    return seen


def canonical_course(courses: Sequence):
    """Fiche qui représente l'item : celle rattachée au collège du référentiel.

    Le référentiel UNESS fait autorité sur l'association collège-item, ce qui
    donne un rattachement stable indépendant de l'organisation personnelle. À
    défaut de correspondance, la plus ancienne fiche fait référence — un choix
    déterministe vaut mieux qu'un ordre de chargement.
    """
    if not courses:
        raise ValueError("Un item doit avoir au moins une fiche")
    if len(courses) == 1:
        return courses[0]

    item = normalized_item(courses[0])
    referential_colleges = item_colleges(item) if item else ()
    if referential_colleges:
        for referential_college in referential_colleges:
            for course in courses:
                colleges = [str(c).strip() for c in (getattr(course, "college", None) or [])]
                normalized = {college.casefold() for college in colleges}
                if referential_college.casefold() in normalized:
                    return course

    return min(courses, key=lambda c: (getattr(c, "created_time", None) or 0, str(c.id)))


def canonical_course_for_item(course, courses: Iterable):
    """Return the canonical fiche for ``course``'s item.

    Detail pages can be reached through any college fiche.  Resource actions
    such as the official PDF must nevertheless follow the canonical fiche
    shown by the item page, otherwise the breadcrumb and the opened resource
    can point to different colleges.
    """
    item = normalized_item(course)
    if not item:
        return course
    siblings = [candidate for candidate in courses if normalized_item(candidate) == item]
    return canonical_course(siblings) if siblings else course


def course_for_college(course, college: str, courses: Iterable):
    """Return the item's fiche attached to ``college``, when it exists."""
    requested = str(college or "").strip().casefold()
    if not requested:
        return None
    item = normalized_item(course)
    if not item:
        return None
    for candidate in courses:
        if normalized_item(candidate) != item:
            continue
        candidate_colleges = {
            str(name).strip().casefold()
            for name in (getattr(candidate, "college", None) or [])
            if str(name).strip()
        }
        if requested in candidate_colleges:
            return candidate
    return None


def college_for_item_view(course, requested_college: str | None, courses: Iterable) -> str:
    """Collège à afficher et à utiliser pour les ressources de la vue item.

    Une navigation depuis un collège est contextuelle : elle doit conserver la
    fiche et le PDF de ce collège, même si l'accès direct à l'item utilise la
    fiche principale. Sans contexte, le premier collège du référentiel reste le
    fallback stable.
    """
    siblings = [candidate for candidate in courses if normalized_item(candidate) == normalized_item(course)]
    if not siblings:
        siblings = [course]

    if requested_college:
        selected = course_for_college(course, requested_college, siblings)
        if selected:
            wanted = str(requested_college).strip().casefold()
            for label in getattr(selected, "college", None) or []:
                if str(label).strip().casefold() == wanted:
                    return str(label).strip()

    available = colleges_of_item(siblings)
    for referential in item_colleges(normalized_item(course)):
        for label in available:
            if label.casefold() == referential.casefold():
                return label
    return available[0] if available else ""


def dedupe_by_item(courses: Sequence) -> list:
    """Une seule fiche par item dans la collection reçue, ordre conservé.

    Cette fonction déduplique ce qu'on lui passe ; elle ne reconstitue pas les
    collèges d'un item après un filtrage. Les vues qui doivent afficher tous les
    items d'un collège doivent donc filtrer leur catalogue d'items en amont,
    puis choisir une fiche représentative.

    Deux fiches d'un même item peuvent porter le même collège : la liste de ce
    collège afficherait alors deux fois le même item. Mesuré sur les données
    réelles : 207 lignes en double réparties sur 28 collèges.

    Les cours sans item — ceux d'avant l'externat, organisés par UE et non par
    collège — n'ont pas de doublon possible et sont tous conservés.
    """
    groups = group_courses_by_item(courses)
    keepers = {id(canonical_course(fiches)) for fiches in groups.values()}
    return [
        course
        for course in courses
        if not normalized_item(course) or id(course) in keepers
    ]


def alias_map(courses: Iterable) -> dict[str, tuple[str, ...]]:
    """Pour chaque fiche, l'ensemble des fiches qui décrivent le même item.

    Une fiche sans item est seule dans son groupe : avant l'externat les cours
    n'étaient organisés ni par collège ni par item, ils n'ont pas d'alias.
    """
    courses = list(courses)
    groups = group_courses_by_item(courses)
    by_item = {
        item: tuple(str(c.id) for c in fiches) for item, fiches in groups.items()
    }
    mapping: dict[str, tuple[str, ...]] = {}
    for course in courses:
        item = normalized_item(course)
        mapping[str(course.id)] = by_item.get(item) or (str(course.id),)
    return mapping


def merge_course_map(mapping: dict, aliases: dict[str, tuple[str, ...]]) -> dict:
    """Rassemble les preuves des fiches d'un même item sous chacune d'elles.

    Réviser un item depuis sa fiche Chirurgie digestive doit compter quand on
    le regarde depuis sa fiche Orthopédie : sans cela l'historique reste éclaté
    et la maîtrise est calculée sur une fraction des preuves.
    """
    merged: dict = {}
    for course_id, sibling_ids in aliases.items():
        gathered: list = []
        for sibling in sibling_ids:
            gathered.extend(mapping.get(sibling) or [])
        merged[course_id] = gathered
    for course_id, rows in mapping.items():
        merged.setdefault(course_id, list(rows or []))
    return merged


def referential_college(course) -> str:
    """Collège officiel de l'item de ce cours, ou '' s'il est inconnu."""
    item = normalized_item(course)
    if not item:
        return ""
    colleges = item_colleges(item)
    return colleges[0] if colleges else ""
