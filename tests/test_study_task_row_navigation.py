import inspect
from pathlib import Path

from frontend.components.study_task_row import study_task_row


def test_study_task_row_supports_distinct_single_and_double_click_callbacks():
    params = inspect.signature(study_task_row).parameters
    assert "on_select" in params
    assert "on_double_click" in params


def test_study_task_row_defers_single_click_so_double_click_can_win():
    source = Path("frontend/components/study_task_row.py").read_text(encoding="utf-8")
    assert "SINGLE_CLICK_DELAY" in source
    assert ".cancel()" in source
