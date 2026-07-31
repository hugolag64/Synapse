"""Tests for the one-off backfill of pre-existing UNESS sessions into uness_annales."""

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


def _make_legacy_uness_session(course_title: str, source_url: str) -> int:
    """Simulate a session imported before annale_id existed: metadata only, no annale_id set."""
    spec = PracticeSessionSpec(
        practice_kind=PracticeKind.QCM, total_questions=1, closed_questions=1, course_title=course_title
    )
    import_metadata = {
        "uness": {
            "provenance": {"source_url": source_url, "collected_at": "2026-07-30T18:21:37+00:00"},
            "exam": {
                "faculty": "Faculté de médecine de La Réunion",
                "level": "DFASM1",
                "year": 2024,
                "title": course_title,
            },
        }
    }
    question = {
        "kind": "closed",
        "prompt": "Q ?",
        "choices": ["A", "B"],
        "answer": "A",
        "explanation": "Car A.",
        "import_metadata": import_metadata,
    }
    return local_store.create_ai_practice_session(spec=spec, questions=[question], model="uness-verified-local")


def test_backfill_groups_legacy_sessions_by_source_url_and_prompts_once_per_group(monkeypatch) -> None:
    from scripts.uness.backfill_annales import backfill_annales

    session_a = _make_legacy_uness_session(
        "Gériatrie — mDP1", "https://entrainement.uness.fr/annales/course/view.php?id=29135"
    )
    session_b = _make_legacy_uness_session(
        "Gériatrie — DP1", "https://entrainement.uness.fr/annales/course/view.php?id=29135"
    )

    prompts = iter(["matiere"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(prompts))

    backfill_annales()

    annale = local_store.get_uness_annale_by_source_url(
        "https://entrainement.uness.fr/annales/course/view.php?id=29135"
    )
    assert annale is not None
    assert annale["type_annale"] == "matiere"
    assert local_store.get_ai_practice_session_summary(session_a)["annale_id"] == annale["id"]
    assert local_store.get_ai_practice_session_summary(session_b)["annale_id"] == annale["id"]


def test_backfill_skips_sessions_that_already_have_an_annale_id(monkeypatch) -> None:
    from scripts.uness.backfill_annales import backfill_annales

    session_id = _make_legacy_uness_session(
        "Neuro — DP1", "https://entrainement.uness.fr/annales/course/view.php?id=1"
    )
    annale_id = local_store.create_uness_annale(
        source_url="https://entrainement.uness.fr/annales/course/view.php?id=1",
        collected_at="2026-07-30T18:21:37+00:00",
        faculte="F",
        niveau="DFASM1",
        annee=2024,
        matiere="NEURO",
        titre="Neuro",
        type_annale="vrai_concours",
    )
    local_store.set_session_annale_id(session_id, annale_id)

    def _fail(_prompt: str) -> str:
        raise AssertionError("should not prompt")

    monkeypatch.setattr("builtins.input", _fail)

    backfill_annales()  # must not raise, must not prompt

    assert len(local_store.list_uness_annales()) == 1
