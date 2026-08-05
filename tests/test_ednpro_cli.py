import subprocess
import sys


def test_ednpro_collector_script_runs_from_repository_root():
    result = subprocess.run(
        [sys.executable, "scripts/ednpro/collector.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--cdp-url" in result.stdout
