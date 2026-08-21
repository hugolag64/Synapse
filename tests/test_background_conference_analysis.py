import asyncio
from unittest.mock import patch


def test_run_pending_conference_analysis_calls_cycle_without_blocking():
    from backend.core.background import _run_pending_conference_analysis

    with patch(
        "backend.core.conferences.analysis_job_runner.run_conference_analysis_cycle",
        return_value={"created": 1, "submit_submitted": 1, "poll_succeeded": 0},
    ) as mock_cycle:
        asyncio.run(_run_pending_conference_analysis())

    mock_cycle.assert_called_once()
