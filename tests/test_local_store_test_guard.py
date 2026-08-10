"""Le garde qui empêche une suite de tests d'écrire dans la base réelle.

Contexte : l'audit du 10 août 2026 a trouvé 695 lignes de test sur 1358 dans
`ai_usage_logs`, plus des fixtures dans `ai_practice_questions` et `review_history`.
`conftest.py` positionne `SYNAPSE_TEST_DB_PATH`, mais cette protection ne joue que si
elle s'applique avant l'import du module — ce qui n'était pas toujours le cas.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).parents[1]
_PYTHON = _ROOT / ".venv" / "Scripts" / "python.exe"


def _run(code: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    import os

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    env.pop("SYNAPSE_TEST_DB_PATH", None)
    if env_extra:
        env.update(env_extra)
    executable = str(_PYTHON) if _PYTHON.exists() else sys.executable
    return subprocess.run(
        [executable, "-X", "utf8", "-c", code],
        cwd=str(_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_importing_local_store_under_pytest_without_test_db_path_is_refused():
    """Simule le scénario de fuite : pytest chargé, aucune base de test définie."""
    result = _run(
        "import pytest\n"
        "import backend.core.reviews.local_store\n"
    )

    assert result.returncode != 0, (
        "L'import aurait dû échouer : pytest est chargé sans SYNAPSE_TEST_DB_PATH.\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "SYNAPSE_TEST_DB_PATH" in result.stderr


def test_importing_local_store_outside_pytest_stays_allowed():
    """L'application elle-même doit continuer à ouvrir la base réelle."""
    result = _run(
        "import backend.core.reviews.local_store as ls\n"
        "assert ls.DB_PATH.name == 'synapse_local.db', ls.DB_PATH\n"
        "print('ok')\n"
    )

    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "ok" in result.stdout


def test_explicit_test_db_path_disarms_the_guard(tmp_path):
    """Avec une base de test explicite, pytest chargé ne pose plus de problème."""
    result = _run(
        "import pytest\n"
        "import backend.core.reviews.local_store as ls\n"
        "assert ls.DB_PATH.name == 'garde.db', ls.DB_PATH\n"
        "print('ok')\n",
        env_extra={"SYNAPSE_TEST_DB_PATH": str(tmp_path / "garde.db")},
    )

    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "ok" in result.stdout
