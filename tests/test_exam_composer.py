import pytest

from backend.core.practice.models import PracticeKind, PracticeSessionSpec


def _seed_uness_questions(store, *, session_count: int = 5):
    annale_id = store.create_uness_annale(
        source_url="https://uness.example/composer",
        collected_at="2026-08-16T10:00:00+00:00",
        faculte="Faculté test",
        niveau="DFASM1",
        annee=2026,
        matiere="Cardiologie",
        titre="Annale composition",
        type_annale="edn_complet",
    )
    for session_index in range(session_count):
        questions = []
        for question_index in range(2):
            questions.append(
                {
                    "prompt": f"Dossier {session_index} question {question_index}",
                    "choices": ["A", "B"],
                    "answer": '["A"]',
                    "explanation": "Correction officielle.",
                    "kind": "closed",
                    "item_numbers": (str(230 + session_index),),
                    "import_metadata": {
                        "uness": {
                            "provenance": {"source": "UNESS"},
                            "question": {"type_question": "QRM"},
                        }
                    },
                }
            )
        spec = PracticeSessionSpec(
            practice_kind=PracticeKind.DP,
            total_questions=2,
            open_questions=0,
            closed_questions=2,
            item_number=str(230 + session_index),
            item_numbers=(str(230 + session_index),),
            course_id="uness",
            course_title=f"Dossier {session_index}",
        )
        session_id = store.create_ai_practice_session(
            spec=spec, questions=questions, model="uness-verified-local"
        )
        store.set_session_annale_id(session_id, annale_id)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    from backend.core.reviews import local_store

    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "exam-composer.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield local_store
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def test_same_seed_reproduces_the_same_composition(isolated_db):
    from backend.core.uness.exam_composer import compose_exam_session

    _seed_uness_questions(isolated_db)
    first = compose_exam_session(format="series", seed="abc", question_count=4)
    second = compose_exam_session(format="series", seed="abc", question_count=4)

    assert first["source_session_ids"] == second["source_session_ids"]
    assert first["seed"] == "abc"


def test_formats_respect_cardinality_and_deduplicate_questions(isolated_db):
    from backend.core.uness.exam_composer import compose_exam_session

    _seed_uness_questions(isolated_db, session_count=6)
    dp = compose_exam_session(format="dp", seed="dp-seed", dp_count=3)
    series = compose_exam_session(format="series", seed="series-seed", question_count=5)
    mixed = compose_exam_session(format="mixed", seed="mixed-seed", dp_count=2, question_count=4)

    assert len(dp["source_session_ids"]) == 3
    assert len(series["question_ids"]) == 5
    assert len(mixed["question_ids"]) == len(set(mixed["question_ids"]))
    assert mixed["duration_seconds"] == 7200


def test_composer_rejects_insufficient_candidates(isolated_db):
    from backend.core.uness.exam_composer import compose_exam_session

    with pytest.raises(ValueError, match="candidat"):
        compose_exam_session(format="series", seed="empty", question_count=5)
