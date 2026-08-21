"""La couverture EDN se mesure sur les items travaillés, pas sur date_1ere_lecture.

Retour d'usage : le panneau Sprint EDN affichait « ITEMS 8/582 » — le nombre de
fiches portant une `date_1ere_lecture` — alors que l'historique local contenait
163 items EDN avec au moins une révision validée. La progression paraissait
nulle et la projection à l'examen n'avait aucun sens.
"""
import datetime

from backend.core.edn.trajectory import build_progress_snapshot

_AS_OF = datetime.date(2026, 8, 21)


def _done(item_number: str, completed_at: str) -> dict:
    return {"status": "done", "item_number": item_number, "completed_at": completed_at}


def test_coverage_counts_distinct_edn_items_with_a_validated_review():
    history = {
        "a": _done("147", "2026-08-20"),
        "b": _done("147", "2026-03-02"),   # même item, déjà compté
        "c": _done("221", "2026-01-15"),
        "d": {"status": "postponed", "item_number": "330", "completed_at": ""},
    }

    snapshot = build_progress_snapshot(
        tasks=[], history=history, as_of=_AS_OF, total_edn_items=367,
    )

    assert snapshot.covered_items == 2
    assert snapshot.total_items == 367


def test_coverage_ignores_entries_without_an_item_number():
    history = {"a": _done("", "2026-08-20"), "b": _done("147", "2026-08-20")}

    snapshot = build_progress_snapshot(
        tasks=[], history=history, as_of=_AS_OF, total_edn_items=367,
    )

    assert snapshot.covered_items == 1


def test_item_numbers_are_normalised_before_being_counted():
    """« ITEM 147 », « 147 » et « 147 » entourés d'espaces sont le même item."""
    history = {
        "a": _done("ITEM 147", "2026-08-20"),
        "b": _done(" 147 ", "2026-08-19"),
        "c": _done("147", "2026-08-18"),
    }

    snapshot = build_progress_snapshot(
        tasks=[], history=history, as_of=_AS_OF, total_edn_items=367,
    )

    assert snapshot.covered_items == 1


def test_total_defaults_to_the_edn_referential():
    snapshot = build_progress_snapshot(tasks=[], history={}, as_of=_AS_OF)

    assert snapshot.total_items == 367


def test_recent_throughput_counts_items_not_fiches():
    """La projection raisonne en items : la cadence doit être dans la même
    unité que la couverture, sinon on projette des fiches sur des items."""
    history = {
        "a": _done("147", "2026-08-20"),
        "b": _done("147", "2026-08-19"),   # même item, une seule unité de cadence
        "c": _done("221", "2026-08-18"),
        "d": _done("330", "2026-01-01"),   # hors fenêtre de 28 jours
    }

    snapshot = build_progress_snapshot(
        tasks=[], history=history, as_of=_AS_OF, total_edn_items=367,
    )

    assert snapshot.new_items_per_week == 0.5


def test_daily_minutes_come_from_study_sessions():
    """duration_minutes n'existe pas dans review_history : les durées réelles
    vivent dans study_sessions, et le rythme valait 0 en permanence."""
    sessions = [
        {"session_date": "2026-08-20", "duration_minutes": 60},
        {"session_date": "2026-08-18", "duration_minutes": 24},
        {"session_date": "2026-01-01", "duration_minutes": 999},  # hors fenêtre
    ]

    snapshot = build_progress_snapshot(
        tasks=[], history={}, as_of=_AS_OF, study_sessions=sessions,
    )

    assert snapshot.recent_minutes_per_day == round(84 / 28, 2)


def test_daily_minutes_are_zero_without_any_session():
    snapshot = build_progress_snapshot(tasks=[], history={}, as_of=_AS_OF)

    assert snapshot.recent_minutes_per_day == 0.0


def test_throughput_counts_newly_covered_items_not_revisions():
    """Réviser un item déjà couvert n'augmente pas la couverture : la cadence
    qui alimente la projection doit compter les items découverts, sinon elle
    projette 100 % pour quiconque révise régulièrement."""
    history = {
        "vieux": _done("147", "2026-02-01"),      # item déjà couvert…
        "revu": _done("147", "2026-08-20"),       # …et seulement revu depuis
        "nouveau": _done("221", "2026-08-19"),    # première validation récente
    }

    snapshot = build_progress_snapshot(
        tasks=[], history=history, as_of=_AS_OF, total_edn_items=367,
    )

    assert snapshot.covered_items == 2
    assert snapshot.new_items_per_week == 0.25


def test_an_item_first_validated_inside_the_window_counts_once():
    history = {
        "a": _done("221", "2026-08-19"),
        "b": _done("221", "2026-08-20"),
        "c": _done("221", "2026-08-21"),
    }

    snapshot = build_progress_snapshot(
        tasks=[], history=history, as_of=_AS_OF, total_edn_items=367,
    )

    assert snapshot.new_items_per_week == 0.25
