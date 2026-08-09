"""Tests for the annale detail page's data assembly (not full NiceGUI rendering)."""

from __future__ import annotations

import pytest

from backend.core.reviews import local_store
from backend.core.practice.models import PracticeKind, PracticeSessionSpec


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def _make_session(course_title: str) -> int:
    spec = PracticeSessionSpec(
        practice_kind=PracticeKind.QCM,
        total_questions=1,
        closed_questions=1,
        course_title=course_title,
    )
    question = {"kind": "closed", "prompt": "Q ?", "choices": ["A", "B"], "answer": "A", "explanation": "Car A."}
    return local_store.create_ai_practice_session(spec=spec, questions=[question], model="uness-verified-local")


def test_load_annale_detail_returns_annale_and_ordered_sub_parts() -> None:
    from frontend.pages.annale_detail import _load_annale_detail

    annale_id = local_store.create_uness_annale(
        source_url="https://entrainement.uness.fr/annales/course/view.php?id=200",
        collected_at="2026-07-30T18:21:37+00:00",
        faculte="Faculté de médecine de La Réunion",
        niveau="DFASM1",
        annee=2024,
        matiere="GÉRIATRIE",
        titre="Gériatrie 2024",
        type_annale="matiere",
    )
    session_a = _make_session("Gériatrie — mDP1")
    session_b = _make_session("Gériatrie — DP1")
    local_store.set_session_annale_id(session_a, annale_id)
    local_store.set_session_annale_id(session_b, annale_id)

    annale, sessions = _load_annale_detail(annale_id)

    assert annale["titre"] == "Gériatrie 2024"
    assert [row["id"] for row in sessions] == [session_a, session_b]


def test_load_annale_detail_returns_none_for_unknown_id() -> None:
    from frontend.pages.annale_detail import _load_annale_detail

    annale, sessions = _load_annale_detail(999999)

    assert annale is None
    assert sessions == []


def test_annale_detail_uses_a_linear_subpart_list() -> None:
    from pathlib import Path

    source = Path("frontend/pages/annale_detail.py").read_text(encoding="utf-8")

    assert ".an-part-row" in source
    assert "grid-template-columns:minmax(240px, 1.4fr) 160px 130px" in source
    assert "STATUT" in source
    assert "ACTION" in source


def test_annale_detail_exposes_a_continuous_exam_action():
    from pathlib import Path

    source = Path("frontend/pages/annale_detail.py").read_text(encoding="utf-8")

    assert "Mode concours continu" in source
    assert "_open_continuous_exam" in source
    assert "on_complete=_after_continuous_exam" in source
