"""Tests for the uness_annales grouping table and its local_store CRUD."""

from __future__ import annotations

import sqlite3

import pytest

from backend.core.reviews import local_store
from backend.core.practice.models import (
    PracticeDifficulty,
    PracticeKind,
    PracticeSessionSpec,
)


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
        open_questions=0,
        closed_questions=1,
        course_title=course_title,
    )
    question = {
        "kind": "closed",
        "prompt": "Q ?",
        "choices": ["A", "B"],
        "answer": "A",
        "explanation": "Car A.",
    }
    return local_store.create_ai_practice_session(spec=spec, questions=[question], model="uness-verified-local")


def _complete_session(session_id: int, score_percent: float) -> None:
    question_id = local_store.get_ai_practice_session(session_id)[0]["id"]
    local_store.record_ai_practice_attempt(
        session_id=session_id,
        question_id=question_id,
        response="A",
        is_correct=True,
        score_percent=score_percent,
    )


def test_create_and_fetch_annale_by_source_url() -> None:
    annale_id = local_store.create_uness_annale(
        source_url="https://entrainement.uness.fr/annales/course/view.php?id=1",
        collected_at="2026-07-30T18:21:37+00:00",
        faculte="Faculté de médecine de La Réunion",
        niveau="DFASM1",
        annee=2024,
        matiere="GÉRIATRIE",
        titre="DFASM1_UE4S7_CT_Gériatrie_080224",
        type_annale="matiere",
    )

    fetched = local_store.get_uness_annale_by_source_url(
        "https://entrainement.uness.fr/annales/course/view.php?id=1"
    )

    assert fetched is not None
    assert fetched["id"] == annale_id
    assert fetched["matiere"] == "GÉRIATRIE"
    assert fetched["type_annale"] == "matiere"


def test_source_url_lookup_ignores_fragment_and_trailing_slash() -> None:
    """The same UNESS course page is sometimes collected once with a
    "#section-0" anchor and once without — both must resolve to the same
    annale instead of silently spawning an empty duplicate."""
    annale_id = local_store.create_uness_annale(
        source_url="https://entrainement.uness.fr/annales/course/view.php?id=5#section-0",
        collected_at="2026-07-30T18:21:37+00:00",
        faculte="Faculté de médecine de La Réunion",
        niveau="DFASM1",
        annee=2024,
        matiere="CARDIOLOGIE",
        titre="DFASM1_UE_Cardio",
        type_annale="matiere",
    )

    fetched = local_store.get_uness_annale_by_source_url(
        "https://entrainement.uness.fr/annales/course/view.php?id=5"
    )

    assert fetched is not None
    assert fetched["id"] == annale_id


def test_create_annale_rejects_duplicate_source_url_across_fragment_variants() -> None:
    local_store.create_uness_annale(
        source_url="https://entrainement.uness.fr/annales/course/view.php?id=6",
        collected_at="2026-07-30T18:21:37+00:00",
        faculte="Faculté de médecine de La Réunion",
        niveau="DFASM1",
        annee=2024,
        matiere="NEUROLOGIE",
        titre="DFASM1_UE_Neuro",
        type_annale="matiere",
    )

    with pytest.raises(sqlite3.IntegrityError):
        local_store.create_uness_annale(
            source_url="https://entrainement.uness.fr/annales/course/view.php?id=6#section-0",
            collected_at="2026-07-30T18:21:37+00:00",
            faculte="Faculté de médecine de La Réunion",
            niveau="DFASM1",
            annee=2024,
            matiere="NEUROLOGIE",
            titre="DFASM1_UE_Neuro",
            type_annale="matiere",
        )


def test_create_annale_rejects_duplicate_source_url() -> None:
    kwargs = dict(
        source_url="https://entrainement.uness.fr/annales/course/view.php?id=2",
        collected_at="2026-07-30T18:21:37+00:00",
        faculte="Faculté de médecine de La Réunion",
        niveau="DFASM1",
        annee=2024,
        matiere="NEUROLOGIE",
        titre="DFASM1_UE_Neuro",
        type_annale="matiere",
    )
    local_store.create_uness_annale(**kwargs)

    with pytest.raises(sqlite3.IntegrityError):
        local_store.create_uness_annale(**kwargs)


def test_identity_lookup_finds_same_exam_when_source_url_changes() -> None:
    local_store.create_uness_annale(
        source_url="https://example.test/one",
        collected_at="2026-08-07T08:00:00+00:00",
        faculte="EDNpro",
        niveau="EDN",
        annee=2023,
        matiere="Cardiologie",
        titre="EDN 2023 — P1",
        type_annale="edn_complet",
        source="EDNpro",
    )

    found = local_store.get_uness_annale_by_identity(
        source="EDNpro",
        annee=2023,
        matiere="Cardiologie",
        titre="EDN 2023 — P1",
    )

    assert found is not None
    assert found["source_url"] == "https://example.test/one"


def test_list_uness_annales_aggregates_sub_part_scores_and_supports_filters() -> None:
    annale_id = local_store.create_uness_annale(
        source_url="https://entrainement.uness.fr/annales/course/view.php?id=3",
        collected_at="2026-07-30T18:21:37+00:00",
        faculte="Faculté de médecine de La Réunion",
        niveau="DFASM1",
        annee=2024,
        matiere="GÉRIATRIE",
        titre="DFASM1_UE4S7_CT_Gériatrie_080224",
        type_annale="matiere",
    )
    session_a = _make_session("Gériatrie — mDP1")
    session_b = _make_session("Gériatrie — DP1")
    local_store.set_session_annale_id(session_a, annale_id)
    local_store.set_session_annale_id(session_b, annale_id)
    _complete_session(session_a, 80.0)

    matching = local_store.list_uness_annales(matiere="GÉRIATRIE")
    assert len(matching) == 1
    row = matching[0]
    assert row["id"] == annale_id
    assert row["total_parts"] == 2
    assert row["completed_parts"] == 1
    assert row["avg_score"] == pytest.approx(80.0)

    assert local_store.list_uness_annales(matiere="CARDIOLOGIE") == []
    assert local_store.list_uness_annales(faculte="Faculté de médecine de La Réunion") != []
    assert local_store.list_uness_annales(annee=2025) == []
    assert local_store.list_uness_annales(type_annale="concours_blanc") == []


def test_list_annale_sessions_returns_pending_and_completed_status() -> None:
    annale_id = local_store.create_uness_annale(
        source_url="https://entrainement.uness.fr/annales/course/view.php?id=4",
        collected_at="2026-07-30T18:21:37+00:00",
        faculte="Faculté de médecine de La Réunion",
        niveau="DFASM1",
        annee=2024,
        matiere="GÉRIATRIE",
        titre="DFASM1_UE4S7_CT_Gériatrie_080224",
        type_annale="matiere",
    )
    session_a = _make_session("Gériatrie — mDP1")
    session_b = _make_session("Gériatrie — DP1")
    local_store.set_session_annale_id(session_a, annale_id)
    local_store.set_session_annale_id(session_b, annale_id)
    _complete_session(session_a, 80.0)

    rows = local_store.list_annale_sessions(annale_id)

    assert [row["id"] for row in rows] == [session_a, session_b]
    assert rows[0]["status"] == "completed"
    assert rows[1]["status"] == "pending"


def test_ai_practice_session_defaults_to_null_annale_id() -> None:
    session_id = _make_session("QCM classique")
    assert local_store.get_ai_practice_session_summary(session_id)["annale_id"] is None
