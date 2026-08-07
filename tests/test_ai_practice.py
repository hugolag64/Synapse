import json
from types import SimpleNamespace

import pytest

from backend.core.ai.routing import AIModel, AIResponse
from backend.core.practice.mastery import record_ai_practice_mastery
from backend.core.practice.models import (
    GeneratedQuestion,
    PracticeDifficulty,
    PracticeKind,
    PracticeSessionSpec,
    QuestionKind,
)
from backend.core.practice.service import PracticeGenerationError, PracticeService
from backend.core.reviews import local_store
from frontend.components.qcm_replay import _same_closed_answer, save_response_once


@pytest.fixture()
def practice_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "practice.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def spec(**overrides):
    values = dict(
        practice_kind=PracticeKind.QCM,
        total_questions=3,
        open_questions=1,
        closed_questions=2,
        item_number="115",
        course_id="course-115",
        course_title="Insuffisance cardiaque",
    )
    values.update(overrides)
    return PracticeSessionSpec(**values)


def test_spec_requires_exact_open_closed_distribution():
    with pytest.raises(ValueError, match="somme"):
        spec(total_questions=4)


def test_practice_spec_defaults_to_edn_difficulty():
    session = spec()
    assert session.difficulty is PracticeDifficulty.EDN


def test_practice_spec_rejects_unknown_difficulty():
    with pytest.raises(ValueError, match="difficulté"):
        spec(difficulty="unknown")


def test_generation_dialog_uses_compact_centered_linear_controls():
    import inspect

    from frontend.components import ai_practice_panel

    source = inspect.getsource(ai_practice_panel._open_generation_dialog)
    assert "width: 620px" in source
    assert "border-radius: 8px" in source
    assert "max-width: calc(100vw - 32px)" in source
    assert "ai-practice-kind-toggle" in source
    assert "label-always" not in source
    assert "total_value_chip" in source


def test_generation_dialog_normalizes_qcm_toggle_value_to_enum():
    import inspect

    from frontend.components import ai_practice_panel

    source = inspect.getsource(ai_practice_panel._open_generation_dialog)
    assert "PracticeKind(str(kind.value).upper())" in source


def test_generation_dialog_exposes_edn_difficulty_by_default():
    import inspect

    from frontend.components import ai_practice_panel

    source = inspect.getsource(ai_practice_panel._open_generation_dialog)
    assert 'PracticeDifficulty.STANDARD.value: "Standard"' in source
    assert 'PracticeDifficulty.EDN.value: "EDN"' in source
    assert 'PracticeDifficulty.DIFFICULT.value: "Difficile"' in source
    assert 'PracticeDifficulty.CONCOURS.value: "Concours"' in source
    assert "value=PracticeDifficulty.EDN.value" in source
    assert "difficulty=PracticeDifficulty(str(difficulty.value))" in source


def test_generation_dialog_can_open_or_only_conserve_the_session():
    import inspect

    from frontend.components import ai_practice_panel

    source = inspect.getsource(ai_practice_panel._open_generation_dialog)
    assert "open_after_generation" in source
    assert "Ouvrir directement la session pour répondre" in source
    assert "if open_after_generation.value" in source


def test_dp_tutor_uses_a_guided_configurable_wizard_with_retry():
    from pathlib import Path

    source = Path("frontend/components/ai_practice_panel.py").read_text(encoding="utf-8")

    assert "Tuteur DP · étape 1/3" in source
    assert "total_questions = ui.select" in source
    assert "max_attempts=2" in source
    assert "Ouvrir la session" in source
    assert "dialog.close()" in source


def test_closed_qcm_accepts_multiple_correct_choices_in_any_order():
    choices = ["HTA", "Tabac", "Âge"]
    assert _same_closed_answer("Tabac, HTA", "A, B", choices)
    assert not _same_closed_answer("HTA", "A, B", choices)


def test_generated_question_requires_correction_and_explanation():
    with pytest.raises(ValueError, match="correction"):
        GeneratedQuestion("Question", QuestionKind.OPEN, "", "explication")


def test_practice_parser_keeps_mixed_distribution():
    payload = {"questions": [
        {"kind": "open", "prompt": "P1", "answer": "A1", "explanation": "E1"},
        {"kind": "closed", "prompt": "P2", "choices": ["A", "B"], "answer": "A", "explanation": "E2"},
        {"kind": "closed", "prompt": "P3", "choices": ["A", "B"], "answer": "B", "explanation": "E3"},
    ]}
    from backend.core.practice.service import _parse_questions
    parsed = _parse_questions(payload, spec())
    assert [q.kind for q in parsed] == [QuestionKind.OPEN, QuestionKind.CLOSED, QuestionKind.CLOSED]


def test_practice_parser_accepts_fenced_json_from_provider():
    from backend.core.practice.service import _parse_questions

    payload = '''Voici la session :
```json
{"questions":[{"kind":"open","prompt":"P1","answer":"A1","explanation":"E1"},{"kind":"closed","prompt":"P2","choices":["A","B"],"answer":"A","explanation":"E2"},{"kind":"closed","prompt":"P3","choices":["A","B"],"answer":"B","explanation":"E3"}]}
```
'''

    parsed = _parse_questions(payload, spec())

    assert len(parsed) == 3
    assert parsed[0].prompt == "P1"


def test_parser_rejects_wrong_distribution():
    from backend.core.practice.service import _parse_questions
    payload = {"questions": [
        {"kind": "closed", "prompt": "P1", "choices": ["A", "B"], "answer": "A", "explanation": "E1"},
        {"kind": "closed", "prompt": "P2", "choices": ["A", "B"], "answer": "A", "explanation": "E2"},
        {"kind": "closed", "prompt": "P3", "choices": ["A", "B"], "answer": "B", "explanation": "E3"},
    ]}
    with pytest.raises(PracticeGenerationError, match="répartition"):
        _parse_questions(payload, spec())


def test_create_replay_and_attempt_history(practice_db):
    questions = [
        {"prompt": "Question ouverte", "kind": QuestionKind.OPEN, "choices": [], "answer": "Réponse", "explanation": "Pourquoi"},
        {"prompt": "Question fermée", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "A", "explanation": "Correction"},
        {"prompt": "Question fermée 2", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "B", "explanation": "Correction 2"},
    ]
    first = local_store.create_ai_practice_session(
        spec=spec(difficulty=PracticeDifficulty.CONCOURS),
        questions=questions,
        model="gemini-3.1-flash-lite",
    )
    assert local_store.get_ai_practice_sessions(limit=1)[0]["difficulty"] == "concours"
    first_rows = local_store.get_ai_practice_session(first)
    assert [row["prompt"] for row in first_rows] == [q["prompt"] for q in questions]

    local_store.record_ai_practice_attempt(
        session_id=first, question_id=first_rows[0]["id"], response="Réponse",
        is_correct=True, score_percent=100,
    )
    replay = local_store.replay_ai_practice_session(first)
    assert local_store.get_ai_practice_sessions(limit=1)[0]["difficulty"] == "concours"
    replay_rows = local_store.get_ai_practice_session(replay)
    assert [row["id"] for row in replay_rows] == [row["id"] for row in first_rows]
    assert replay_rows[0]["attempts"] == []

    history = local_store.get_ai_practice_history(item_number="115")
    assert len(history) == 2
    assert history[0]["session"]["difficulty"] == "concours"
    assert history[1]["questions"][0]["attempts"][0]["response"] == "Réponse"


def test_empty_ai_practice_session_cannot_be_replayed(practice_db):
    session_id = local_store.create_ai_practice_session(
        spec=spec(), questions=[], model="test-model",
    )

    with pytest.raises(ValueError, match="questions"):
        local_store.replay_ai_practice_session(session_id)

    assert [row["id"] for row in local_store.get_ai_practice_sessions(limit=10)] == [session_id]


def test_ai_practice_session_summary_uses_latest_attempt_per_question(practice_db):
    questions = [
        {"prompt": "Q1", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "A", "explanation": "E1"},
        {"prompt": "Q2", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "B", "explanation": "E2"},
        {"prompt": "Q3", "kind": QuestionKind.OPEN, "choices": [], "answer": "C", "explanation": "E3"},
    ]
    session_id = local_store.create_ai_practice_session(
        spec=spec(), questions=questions, model="test-model",
    )
    rows = local_store.get_ai_practice_session(session_id)
    first_attempt_id = local_store.record_ai_practice_attempt(
        session_id=session_id, question_id=rows[0]["id"], response="A", is_correct=False, score_percent=0,
    )
    local_store.record_ai_practice_attempt(
        session_id=session_id, question_id=rows[0]["id"], response="A", is_correct=True, score_percent=100,
    )
    second_attempt_id = local_store.record_ai_practice_attempt(
        session_id=session_id, question_id=rows[1]["id"], response="A", is_correct=False, score_percent=0,
    )

    summary = local_store.get_ai_practice_session_summary(session_id)

    assert summary["answered_count"] == 2
    assert summary["scored_count"] == 2
    assert summary["correct_count"] == 1
    assert summary["incorrect_count"] == 1
    assert summary["unanswered_count"] == 1
    assert len(summary["latest_attempts"]) == 2
    assert {attempt["id"] for attempt in summary["latest_attempts"]} == {
        first_attempt_id + 1, second_attempt_id,
    }
    assert first_attempt_id not in {attempt["id"] for attempt in summary["latest_attempts"]}


def test_partial_scored_attempt_does_not_complete_session(practice_db):
    session_id = local_store.create_ai_practice_session(
        spec=spec(total_questions=2, open_questions=0, closed_questions=2),
        questions=[
            {"prompt": "Q1", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "A", "explanation": "E1"},
            {"prompt": "Q2", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "B", "explanation": "E2"},
        ],
        model="test-model",
    )
    first_question = local_store.get_ai_practice_session(session_id)[0]

    local_store.record_ai_practice_attempt(
        session_id=session_id, question_id=first_question["id"], response="A",
        is_correct=True, score_percent=100, finalize_session=False,
    )

    summary = local_store.get_ai_practice_session_summary(session_id)
    assert summary["score_percent"] is None
    assert summary["completed_at"] is None


def test_finalizing_partial_session_keeps_it_draft_and_unrecorded(practice_db):
    session_id = local_store.create_ai_practice_session(
        spec=spec(total_questions=2, open_questions=0, closed_questions=2),
        questions=[
            {"prompt": "Q1", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "A", "explanation": "E1"},
            {"prompt": "Q2", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "B", "explanation": "E2"},
        ],
        model="test-model",
    )
    first_question = local_store.get_ai_practice_session(session_id)[0]
    local_store.record_ai_practice_attempt(
        session_id=session_id, question_id=first_question["id"], response="A",
        is_correct=True, score_percent=100, finalize_session=False,
    )

    summary = local_store.finalize_ai_practice_session(session_id)

    assert summary["completion_state"] == "draft"
    assert summary["missing_positions"] == [2]
    assert summary["completed_at"] is None
    assert record_ai_practice_mastery(session_id) is None


def test_incorrect_answer_finalizes_when_weak_point_creation_fails(practice_db, monkeypatch):
    session_id = local_store.create_ai_practice_session(
        spec=spec(total_questions=1, open_questions=0, closed_questions=1),
        questions=[{"prompt": "Q1", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "A", "explanation": "E1"}],
        model="test-model",
    )
    question = local_store.get_ai_practice_session(session_id)[0]
    local_store.record_ai_practice_attempt(
        session_id=session_id, question_id=question["id"], response="B",
        is_correct=False, score_percent=0, finalize_session=False,
    )
    monkeypatch.setattr(local_store, "add_weak_point", lambda **_: (_ for _ in ()).throw(RuntimeError("lacune indisponible")))

    summary = local_store.finalize_ai_practice_session(session_id)

    assert summary["completion_state"] == "scored"
    assert summary["completed_at"] is not None


def test_reliable_practice_migration_is_idempotent(practice_db):
    local_store.init_db()
    local_store.init_db()

    with local_store._conn() as con:
        columns = {
            row["name"]
            for row in con.execute("PRAGMA table_info(ai_practice_sessions)").fetchall()
        }
        tables = {
            row["name"]
            for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }

    assert {"completion_state", "score_mode", "score_reason"} <= columns
    assert {
        "ai_practice_attempt_propositions",
        "ai_practice_question_items",
    } <= tables


def test_explicit_finalization_completes_deferred_scored_attempts(practice_db):
    session_id = local_store.create_ai_practice_session(
        spec=spec(total_questions=2, open_questions=0, closed_questions=2),
        questions=[
            {"prompt": "Q1", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "A", "explanation": "E1"},
            {"prompt": "Q2", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "B", "explanation": "E2"},
        ],
        model="test-model",
    )
    rows = local_store.get_ai_practice_session(session_id)
    for question, response, correct in zip(rows, ("A", "A"), (True, False), strict=True):
        local_store.record_ai_practice_attempt(
            session_id=session_id, question_id=question["id"], response=response,
            is_correct=correct, score_percent=100 if correct else 0, finalize_session=False,
        )

    completed = local_store.finalize_ai_practice_session(session_id)
    assert completed["score_percent"] == 50.0
    assert completed["completed_at"] is not None


def test_reader_retry_does_not_duplicate_persisted_attempt(practice_db):
    session_id = local_store.create_ai_practice_session(
        spec=spec(total_questions=1, open_questions=0, closed_questions=1),
        questions=[{"prompt": "Q1", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "A", "explanation": "E1"}],
        model="test-model",
    )
    question = local_store.get_ai_practice_session(session_id)[0]
    persisted = {}

    def save() -> None:
        local_store.record_ai_practice_attempt(
            session_id=session_id, question_id=question["id"], response="A",
            is_correct=True, score_percent=100, finalize_session=False,
        )

    save_response_once(persisted, question["id"], "A", save)
    save_response_once(persisted, question["id"], "A", save)

    assert len(local_store.get_ai_practice_session(session_id)[0]["attempts"]) == 1


def test_ai_practice_sessions_history_filter_matches_title_and_status(practice_db):
    pending = local_store.create_ai_practice_session(
        spec=spec(course_title="Cardio avancée", item_number="115"),
        questions=[{"prompt": "Q1", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "A", "explanation": "E"}],
        model="test-model",
    )
    completed = local_store.create_ai_practice_session(
        spec=spec(course_title="Neurologie", item_number="215"),
        questions=[{"prompt": "Q1", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "A", "explanation": "E"}],
        model="test-model",
    )
    completed_question_id = local_store.get_ai_practice_session(completed)[0]["id"]
    local_store.record_ai_practice_attempt(
        session_id=completed, question_id=completed_question_id, response="A", is_correct=True, score_percent=100,
    )
    local_store.finalize_ai_practice_session(completed)

    assert [row["id"] for row in local_store.get_ai_practice_sessions_history(query="CARDIO")] == [pending]
    assert [row["id"] for row in local_store.get_ai_practice_sessions_history(query="215")] == [completed]
    assert [row["id"] for row in local_store.get_ai_practice_sessions_history(status="pending")] == [pending]
    assert [row["id"] for row in local_store.get_ai_practice_sessions_history(status="completed")] == [completed]


def test_delete_pending_ai_practice_session_removes_only_the_pending_session(practice_db):
    pending = local_store.create_ai_practice_session(
        spec=spec(course_title="Session à supprimer", item_number="115"),
        questions=[{"prompt": "Q1", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "A", "explanation": "E"}],
        model="test-model",
    )

    assert local_store.delete_pending_ai_practice_session(pending) is True
    assert local_store.get_ai_practice_sessions_history(status="pending") == []
    assert local_store.get_ai_practice_session(pending) == []


def test_delete_pending_ai_practice_session_does_not_delete_completed_session(practice_db):
    completed = local_store.create_ai_practice_session(
        spec=spec(course_title="Session terminée", item_number="215"),
        questions=[{"prompt": "Q1", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "A", "explanation": "E"}],
        model="test-model",
    )
    question_id = local_store.get_ai_practice_session(completed)[0]["id"]
    local_store.record_ai_practice_attempt(
        session_id=completed, question_id=question_id, response="A", is_correct=True, score_percent=100,
    )

    assert local_store.delete_pending_ai_practice_session(completed) is False
    assert local_store.get_ai_practice_sessions_history(status="completed")[0]["id"] == completed


def test_delete_ai_practice_session_removes_completed_session(practice_db):
    session_id = local_store.create_ai_practice_session(
        spec=spec(course_title="Session historique", item_number="215"),
        questions=[{"prompt": "Q1", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "A", "explanation": "E"}],
        model="test-model",
    )

    assert local_store.delete_ai_practice_session(session_id) is True
    assert local_store.get_ai_practice_session(session_id) == []
    assert local_store.delete_ai_practice_session(session_id) is False


def test_practice_service_routes_dp_to_flash_and_persists():
    class FakeAI:
        def __init__(self):
            self.calls = []

        def generate(self, task, prompt, *, context=None, response_format):
            self.calls.append((task, context, response_format))
            payload = {"questions": [
                {"kind": "open", "prompt": "P", "answer": "A", "explanation": "E"},
            ]}
            return AIResponse(json.dumps(payload), AIModel.FLASH, 10, 10)

    fake = FakeAI()
    svc = PracticeService(ai_service=fake, store=SimpleNamespace(
        create_ai_practice_session=lambda **kwargs: kwargs["spec"].total_questions,
    ))
    result = svc.create_new_session(spec(
        practice_kind=PracticeKind.DP,
        total_questions=1,
        open_questions=1,
        closed_questions=0,
    ))
    assert result == 1
    assert fake.calls[0][0].value == "dp"
    assert fake.calls[0][2] == "json"


def test_practice_service_prompt_mentions_concours_difficulty():
    class FakeAI:
        def __init__(self):
            self.prompt = ""

        def generate(self, task, prompt, *, context=None, response_format):
            self.prompt = prompt
            payload = {"questions": [
                {"kind": "closed", "prompt": "P", "choices": ["A", "B"], "answer": "A", "explanation": "E"},
            ]}
            return AIResponse(json.dumps(payload), AIModel.FLASH, 10, 10)

    fake = FakeAI()
    service = PracticeService(ai_service=fake, store=SimpleNamespace(
        create_ai_practice_session=lambda **kwargs: 1,
    ))
    service.create_new_session(spec(
        total_questions=1,
        open_questions=0,
        closed_questions=1,
        difficulty=PracticeDifficulty.CONCOURS,
    ))
    assert "niveau Concours" in fake.prompt
    assert "distracteurs très proches" in fake.prompt


def test_tutor_dp_retries_wrong_question_count_before_persisting(practice_db):
    class FakeAI:
        def __init__(self):
            self.calls = 0

        def generate(self, task, prompt, *, context=None, response_format):
            self.calls += 1
            count = 1 if self.calls == 1 else 2
            payload = {"questions": [
                {
                    "kind": "closed",
                    "prompt": f"Q{i}",
                    "choices": ["A", "B"],
                    "answer": "A",
                    "explanation": "E",
                }
                for i in range(count)
            ]}
            return AIResponse(json.dumps(payload), AIModel.FLASH, 10, 10)

    fake = FakeAI()
    service = PracticeService(ai_service=fake, store=local_store)

    session_id = service.create_tutor_dp_session(
        item_number="115",
        course_id="course-115",
        course_title="Insuffisance cardiaque",
        dossier_context="Patient avec dyspnée.",
        errors=[],
        gap_details=[],
        total_questions=2,
        max_attempts=2,
    )

    assert fake.calls == 2
    assert len(local_store.get_ai_practice_session(session_id)) == 2


def test_tutor_dp_does_not_persist_after_exhausted_count_retry(practice_db):
    class FakeAI:
        def generate(self, task, prompt, *, context=None, response_format):
            payload = {"questions": [{
                "kind": "closed",
                "prompt": "",
                "choices": ["A", "B"],
                "answer": "A",
                "explanation": "",
            }]}
            return AIResponse(json.dumps(payload), AIModel.FLASH, 10, 10)

    service = PracticeService(ai_service=FakeAI(), store=local_store)

    with pytest.raises(PracticeGenerationError, match="invalide"):
        service.create_tutor_dp_session(
            item_number="115",
            course_id="course-115",
            course_title="Insuffisance cardiaque",
            dossier_context="Patient avec dyspnée.",
            errors=[],
            gap_details=[],
            total_questions=2,
            max_attempts=2,
        )

    assert local_store.get_ai_practice_sessions(limit=10) == []


def test_tutor_dp_recovers_partial_provider_responses_one_question_at_a_time(practice_db):
    class FakeAI:
        def __init__(self):
            self.calls = 0

        def generate(self, task, prompt, *, context=None, response_format):
            self.calls += 1
            payload = {"questions": [{
                "kind": "closed",
                "prompt": f"Question {self.calls}",
                "choices": ["A", "B"],
                "answer": "A",
                "explanation": "E",
            }]}
            return AIResponse(json.dumps(payload), AIModel.FLASH, 10, 10)

    fake = FakeAI()
    service = PracticeService(ai_service=fake, store=local_store)

    session_id = service.create_tutor_dp_session(
        item_number="152",
        course_id="course-152",
        course_title="Endocardite infectieuse",
        dossier_context="Patient fébrile.",
        errors=[],
        gap_details=[],
        total_questions=3,
        max_attempts=1,
    )

    assert fake.calls == 4
    assert len(local_store.get_ai_practice_session(session_id)) == 3


@pytest.mark.parametrize("total_questions", [0, 11])
def test_tutor_dp_rejects_unreasonable_question_count(practice_db, total_questions):
    service = PracticeService(ai_service=SimpleNamespace(), store=local_store)

    with pytest.raises(ValueError, match="entre 1 et 10"):
        service.create_tutor_dp_session(
            item_number="115",
            course_id="course-115",
            course_title="Insuffisance cardiaque",
            dossier_context="Patient avec dyspnée.",
            errors=[],
            gap_details=[],
            total_questions=total_questions,
        )


def test_scored_ai_session_updates_mastery_evaluation_once(practice_db):
    questions = [
        {"prompt": "Q1", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "A", "explanation": "E1"},
        {"prompt": "Q2", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "B", "explanation": "E2"},
    ]
    session_id = local_store.create_ai_practice_session(
        spec=spec(total_questions=2, open_questions=0, closed_questions=2),
        questions=questions,
        model="gemini-3-flash-preview",
    )
    rows = local_store.get_ai_practice_session(session_id)
    local_store.record_ai_practice_attempt(
        session_id=session_id, question_id=rows[0]["id"], response="A", is_correct=True, score_percent=100,
    )
    local_store.record_ai_practice_attempt(
        session_id=session_id, question_id=rows[1]["id"], response="A", is_correct=False, score_percent=0,
    )

    outcome = record_ai_practice_mastery(session_id)
    assert outcome is not None
    stored = local_store.get_qcm_sessions_all(course_id="course-115")
    assert stored[0]["session_type"] == "QCM"
    assert stored[0]["score_percent"] == 50
    assert record_ai_practice_mastery(session_id) is None
