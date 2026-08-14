"""Le profil d'erreurs ne doit pas être perdu quand la question n'est pas classée.

`record_error_signals_for_attempt` s'arrêtait si la question n'avait aucune
ligne dans `ai_practice_question_items`. Mesuré sur les données réelles : sur
37 tentatives, 7 portent sur une question classée, 7 ont le détail
propositionnel, et l'intersection est VIDE. Aucune tentative n'a jamais réuni
les deux conditions — d'où une table `error_signals` à zéro ligne depuis
toujours, sans que rien ne le signale.

Une question d'un dossier hérite de l'item de sa session : mieux vaut ce repli
que perdre le signal.
"""

import pytest

from backend.core.practice import attempt_service
from backend.core.practice.models import PracticeKind, PracticeSessionSpec, QuestionKind
from backend.core.reviews import local_store


@pytest.fixture()
def practice_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "signals.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def _session(item_number: str) -> tuple[int, int]:
    spec = PracticeSessionSpec(
        practice_kind=PracticeKind.QCM,
        total_questions=1,
        open_questions=0,
        closed_questions=1,
        item_number=item_number,
        course_id="course-1",
        course_title="Cours",
    )
    session_id = local_store.create_ai_practice_session(
        spec=spec,
        questions=[{
            "prompt": "Question",
            "kind": QuestionKind.CLOSED,
            "choices": ["A", "B"],
            "answer": "A",
            "explanation": "Parce que.",
        }],
        model="test",
    )
    question_id = local_store.get_ai_practice_session(session_id)[0]["id"]
    return session_id, question_id


def _signals() -> list:
    with local_store._conn() as con:
        return con.execute("SELECT item_number, category FROM error_signals").fetchall()


def test_an_unclassified_question_falls_back_on_its_session_item(practice_db):
    session_id, question_id = _session("230")
    local_store.execute_sql = None  # garde : aucune classification n'est créée

    attempt_service.record_error_signals_for_attempt(
        attempt_id=1,
        question_id=question_id,
        question={"prompt": "Question"},
        propositions=[{"proposition_id": "A", "discordance": "omission"}],
        session_id=session_id,
    )

    assert [row[0] for row in _signals()] == ["230"]


def test_nothing_is_recorded_without_any_item_at_all(practice_db):
    session_id, question_id = _session("")

    attempt_service.record_error_signals_for_attempt(
        attempt_id=1,
        question_id=question_id,
        question={"prompt": "Question"},
        propositions=[{"proposition_id": "A", "discordance": "omission"}],
        session_id=session_id,
    )

    assert _signals() == []


def test_correct_propositions_never_produce_a_signal(practice_db):
    session_id, question_id = _session("230")

    attempt_service.record_error_signals_for_attempt(
        attempt_id=1,
        question_id=question_id,
        question={"prompt": "Question"},
        propositions=[{"proposition_id": "A", "discordance": "correct"}],
        session_id=session_id,
    )

    assert _signals() == []


def test_the_scoring_entry_point_passes_the_session(practice_db):
    """Sans session_id transmis, le repli ne peut pas fonctionner."""
    import inspect

    source = inspect.getsource(attempt_service.score_and_record_closed_attempt)

    assert "session_id=session_id," in source
