import datetime
from types import SimpleNamespace


def test_capacity_is_clamped_to_three_twelve_hours():
    from backend.core.planning.policy import clamp_capacity_hours

    assert clamp_capacity_hours(1) == 3
    assert clamp_capacity_hours(8) == 8
    assert clamp_capacity_hours(99) == 12


def test_capacity_converts_hours_to_existing_minute_api():
    from backend.core.planning.policy import capacity_hours_to_minutes

    assert capacity_hours_to_minutes(3) == 180
    assert capacity_hours_to_minutes(12) == 720


def test_shortcut_vacation_is_inclusive_of_start_and_end():
    from backend.core.planning.policy import vacation_end_date, is_vacation_day

    start = datetime.date(2026, 7, 30)
    end = vacation_end_date(start, 3)
    assert end == datetime.date(2026, 8, 1)
    vacation = {"enabled": True, "start_date": start.isoformat(), "end_date": end.isoformat()}
    assert is_vacation_day(start, vacation)
    assert is_vacation_day(end, vacation)
    assert not is_vacation_day(datetime.date(2026, 8, 2), vacation)


def test_reduced_vacation_halves_capacity_without_going_below_three_hours():
    from backend.core.planning.policy import effective_capacity_minutes

    vacation = {"enabled": True, "strategy": "reduced"}
    assert effective_capacity_minutes(480, vacation) == 240
    assert effective_capacity_minutes(360, vacation) == 180


def test_diagnostic_only_vacation_has_zero_work_capacity():
    from backend.core.planning.policy import effective_capacity_minutes

    vacation = {"enabled": True, "strategy": "diagnostic_only"}
    assert effective_capacity_minutes(480, vacation) == 0


def test_legacy_minute_target_can_be_read_as_capacity_hours():
    from backend.core.planning.policy import capacity_from_preferences

    prefs = {"planning_targets": {"2026-07-28": {"mode": "minutes", "value": 360}}}
    assert capacity_from_preferences(prefs, "2026-07-28") == 360


def test_invalid_or_missing_capacity_defaults_to_six_hours():
    from backend.core.planning.policy import capacity_from_preferences

    assert capacity_from_preferences({}, "2026-07-28") == 360
    assert capacity_from_preferences({"planning_capacity_minutes": 60}, "2026-07-28") == 180


def test_shortcut_payload_for_one_three_and_five_days():
    from backend.core.planning.policy import vacation_payload

    start = datetime.date(2026, 7, 28)
    assert vacation_payload(start, 1)["end_date"] == "2026-07-28"
    assert vacation_payload(start, 3)["end_date"] == "2026-07-30"
    assert vacation_payload(start, 5, "diagnostic_only")["strategy"] == "diagnostic_only"


def test_daily_target_is_reduced_only_inside_vacation_window():
    from backend.core.planning.policy import target_for_day

    prefs = {
        "planning_capacity_minutes": 480,
        "planning_vacation": {
            "enabled": True,
            "start_date": "2026-07-30",
            "end_date": "2026-08-01",
            "strategy": "reduced",
        },
    }
    assert target_for_day(datetime.date(2026, 7, 29), prefs) == 480
    assert target_for_day(datetime.date(2026, 7, 30), prefs) == 240


def test_diagnostic_only_target_is_zero_inside_window():
    from backend.core.planning.policy import target_for_day

    prefs = {
        "planning_capacity_minutes": 480,
        "planning_vacation": {
            "enabled": True,
            "start_date": "2026-07-30",
            "end_date": "2026-08-01",
            "strategy": "diagnostic_only",
        },
    }
    assert target_for_day(datetime.date(2026, 7, 31), prefs) == 0


def test_return_diagnostic_selects_tasks_expected_during_vacation():
    from backend.core.planning.policy import return_diagnostic_tasks

    tasks = [
        SimpleNamespace(id="inside", due_date=datetime.date(2026, 7, 30), priority_score=1),
        SimpleNamespace(id="outside", due_date=datetime.date(2026, 8, 4), priority_score=2),
    ]
    vacation = {
        "enabled": True,
        "start_date": "2026-07-30",
        "end_date": "2026-08-01",
        "strategy": "diagnostic_only",
    }
    result = return_diagnostic_tasks(tasks, vacation, datetime.date(2026, 8, 2))
    assert [task.id for task in result] == ["inside"]
    assert tasks[0].due_date == datetime.date(2026, 7, 30)
