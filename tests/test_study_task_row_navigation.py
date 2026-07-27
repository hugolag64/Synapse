import inspect

from frontend.components.study_task_row import study_task_row


def test_study_task_row_supports_distinct_single_and_double_click_callbacks():
    params = inspect.signature(study_task_row).parameters
    assert "on_select" in params
    assert "on_double_click" in params
