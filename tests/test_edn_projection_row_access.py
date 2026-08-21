"""La projection EDN doit lire l'historique tel que la production le fournit.

`local_store.get_all_history()` retourne des `sqlite3.Row`. Or `_row_value`
retombait sur `getattr`, qui ne voit pas les colonnes d'une Row : chaque ligne
était donc lue comme vide, `new_items_per_week` valait toujours 0, et les
trois scénarios prudent/central/ambitieux tombaient sur la même valeur — la
couverture actuelle, projection nulle.

Les tests existants ne l'attrapaient pas : ils passent des dicts.
"""
import datetime
import sqlite3

from backend.core.edn.trajectory import build_progress_snapshot, project_to_exam

_AS_OF = datetime.date(2026, 8, 21)


def _history_rows() -> dict:
    """Un historique en `sqlite3.Row`, comme get_all_history en renvoie."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute(
        "CREATE TABLE review_history (task_id TEXT, item_number TEXT, status TEXT, "
        "completed_at TEXT)"
    )
    con.executemany(
        "INSERT INTO review_history VALUES (?,?,?,?)",
        [
            ("t1", "147", "done", "2026-08-20"),
            ("t2", "221", "done", "2026-08-18"),
            ("t3", "330", "done", "2026-01-01"),   # hors fenêtre de 28 j
            ("t4", "360", "postponed", ""),
        ],
    )
    rows = con.execute("SELECT * FROM review_history").fetchall()
    return {row["task_id"]: row for row in rows}


def test_sqlite_rows_do_not_expose_columns_as_attributes():
    """Le piège à l'origine du bug, verrouillé explicitement."""
    row = next(iter(_history_rows().values()))

    assert getattr(row, "status", "<absent>") == "<absent>"
    assert row["status"] == "done"
    assert not isinstance(row, dict)


def test_snapshot_counts_completions_from_sqlite_rows():
    snapshot = build_progress_snapshot(
        tasks=[], history=_history_rows(), as_of=_AS_OF, total_edn_items=367,
    )

    # 2 items distincts dans la fenêtre de 28 jours, ramenés à la semaine.
    assert snapshot.new_items_per_week == 0.5


def test_scenarios_diverge_once_the_baseline_is_read():
    """prudent/central/ambitieux valent 0.75/1.0/1.25 fois la même baseline :
    tant qu'elle est nulle, les trois affichent le même chiffre."""
    snapshot = build_progress_snapshot(
        tasks=[], history=_history_rows(), as_of=_AS_OF, total_edn_items=367,
    )
    covered = 40
    snapshot = type(snapshot)(
        covered_items=covered, total_items=582,
        average_mastery=snapshot.average_mastery,
        overdue_reviews=snapshot.overdue_reviews,
        remaining_reviews=snapshot.remaining_reviews,
        new_items_per_week=snapshot.new_items_per_week,
        recent_minutes_per_day=snapshot.recent_minutes_per_day,
    )

    prudent, central, ambitieux = project_to_exam(
        snapshot,
        target_date=datetime.date(2026, 10, 15),
        today=_AS_OF,
    )

    assert prudent.projected_coverage < central.projected_coverage
    assert central.projected_coverage < ambitieux.projected_coverage


def test_projection_does_not_inflate_the_baseline_with_a_capacity_factor():
    """capacity_from_preferences est borné à 180-720 min (policy.py) : le
    facteur `min(1.5, minutes/60)` sature à 1.5 dès 90 min, donc à TOUT réglage
    possible. C'était une inflation constante de 50 %, pas un vrai signal."""
    from backend.core.edn.trajectory import ProgressSnapshot

    snapshot = ProgressSnapshot(
        covered_items=100, total_items=367, average_mastery=50.0,
        overdue_reviews=0, remaining_reviews=0,
        new_items_per_week=7.0, recent_minutes_per_day=10.0,
    )
    weeks = 8
    central = [s for s in project_to_exam(
        snapshot,
        target_date=_AS_OF + datetime.timedelta(weeks=weeks),
        today=_AS_OF,
    ) if s.name == "central"][0]

    expected_items = min(367, 100 + 7.0 * 1.0 * weeks)
    expected_coverage = round(expected_items / 367 * 100, 1)
    assert central.projected_coverage == expected_coverage


def test_project_to_exam_no_longer_takes_a_capacity_parameter():
    """capacity_from_preferences() est borné 180-720 min ; le facteur qu'il
    alimentait saturait à 1.5 dès 90 min — un réglage sans aucun effet
    possible, retiré plutôt que gardé mort."""
    import inspect

    from backend.core.edn.trajectory import project_to_exam as fn

    assert "daily_capacity_minutes" not in inspect.signature(fn).parameters
