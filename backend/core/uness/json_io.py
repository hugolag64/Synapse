"""Lecture et écriture UTF-8 des examens UNESS locaux."""

from __future__ import annotations

import json
from pathlib import Path

from .models import UnessExam, _assert_no_sensitive_data


def load_exam(path: Path) -> UnessExam:
    """Charge un artéfact JSON local et valide son contrat canonique."""
    with Path(path).open(encoding="utf-8") as source:
        return UnessExam.from_dict(json.load(source))


def save_exam(exam: UnessExam, path: Path) -> None:
    """Écrit un artéfact JSON UTF-8 lisible et déterministe localement."""
    payload = exam.to_dict()
    _assert_no_sensitive_data(payload)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as destination:
        json.dump(payload, destination, ensure_ascii=False, indent=2, sort_keys=True)
        destination.write("\n")
