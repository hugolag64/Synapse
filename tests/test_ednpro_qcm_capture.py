"""Contrat d'import des corrections EDNpro observées dans Chromium."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_capture_db(tmp_path, monkeypatch):
    from backend.core.reviews import local_store

    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "capture.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def _raw_question(*, external_id: str, prompt: str, corrected: bool = True) -> dict:
    return {
        "session_id": "session-42",
        "question": {
            "id": external_id,
            "item_number": "221",
            "type": "QCM",
            "rank": "B",
            "prompt": prompt,
            "choices": [
                {"id": "a", "text": "Proposition A", "selected": True, "correct": True},
                {"id": "b", "text": "Proposition B", "selected": False, "correct": False},
            ],
            "simple_explanation": "Explication simple",
            "detailed_explanation": "Explication détaillée par IA",
        },
        "correction": {
            "selected_answers": ["a"],
            "correct_answers": ["a"],
            "score_percent": 100 if corrected else None,
            "is_correct": corrected if corrected else None,
            "displayed": corrected,
        },
    }


def test_normalize_observation_keeps_correction_and_explanations():
    from backend.core.ednpro.qcm_capture import normalize_observation

    observation = normalize_observation(_raw_question(external_id="q-1", prompt="Question 1"))

    assert observation.external_question_id == "q-1"
    assert observation.item_number == "221"
    assert observation.rank == "B"
    assert observation.selected_answers == ("a",)
    assert observation.correct_answers == ("a",)
    assert observation.score_percent == 100.0
    assert observation.corrected is True
    assert observation.explanation_simple == "Explication simple"
    assert observation.explanation_detailed == "Explication détaillée par IA"


def test_extract_corrected_observation_ignores_unanswered_dom_and_reads_rank():
    from backend.core.ednpro.qcm_capture import extract_corrected_observation

    unanswered = """
    <article data-qcm-question="q-dom" data-item-number="230">
      <span>Item 230 · QCM · Rang B</span>
      <h3 data-question-stem>Question visible</h3>
      <label data-choice-id="a"><input type="checkbox">A</label>
    </article>
    """
    assert extract_corrected_observation(unanswered) is None

    corrected = """
    <article data-qcm-question="q-dom" data-item-number="230" data-corrected="true">
      <span>Item 230 · QCM · Rang B</span>
      <h3 data-question-stem>Question visible</h3>
      <label data-choice-id="a" data-selected="true" data-correct="true">A</label>
      <label data-choice-id="b" data-correct="false">B</label>
      <div data-explanation-simple>Explication courte</div>
      <div data-explanation-detailed>Analyse détaillée</div>
    </article>
    """
    observation = extract_corrected_observation(corrected, source_url="https://ednpro.app/objective-session/1")
    assert observation is not None
    assert observation.external_question_id == "q-dom"
    assert observation.item_number == "230"
    assert observation.rank == "B"
    assert observation.selected_answers == ("a",)
    assert observation.correct_answers == ("a",)


def test_import_discards_question_not_yet_corrected_and_is_idempotent():
    from backend.core.ednpro.qcm_capture import normalize_observation, import_session
    from backend.core.reviews import local_store

    session = {
        "external_session_id": "session-42",
        "session_date": "2026-08-10T13:00:00+02:00",
        "questions": [
            normalize_observation(_raw_question(external_id="q-1", prompt="Question 1")),
            normalize_observation(_raw_question(external_id="q-2", prompt="Question 2", corrected=False)),
        ],
    }

    first = import_session(session)
    second = import_session(session)

    assert first.imported_questions == 1
    assert first.discarded_questions == 1
    assert second.imported_questions == 0
    assert second.duplicate_attempts == 1
    with local_store._conn() as con:
        assert con.execute("SELECT COUNT(*) FROM ednpro_qcm_questions").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM ednpro_qcm_attempts").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM ednpro_qcm_sessions").fetchone()[0] == 1


def test_existing_question_is_preserved_but_new_attempt_is_recorded():
    from backend.core.ednpro.qcm_capture import normalize_observation, import_session
    from backend.core.reviews import local_store

    import_session({
        "external_session_id": "session-1",
        "session_date": "2026-08-10",
        "questions": [normalize_observation(_raw_question(external_id="q-1", prompt="Version originale"))],
    })
    result = import_session({
        "external_session_id": "session-2",
        "session_date": "2026-08-11",
        "questions": [normalize_observation(_raw_question(external_id="q-1", prompt="Version modifiée"))],
    })

    assert result.new_questions == 0
    assert result.new_attempts == 1
    with local_store._conn() as con:
        question = con.execute(
            "SELECT prompt FROM ednpro_qcm_questions WHERE external_question_id = ?", ("q-1",)
        ).fetchone()
        assert question["prompt"] == "Version originale"
        assert con.execute("SELECT COUNT(*) FROM ednpro_qcm_attempts").fetchone()[0] == 2


def test_item_stats_expose_correct_wrong_and_rank_counts():
    from backend.core.ednpro.qcm_capture import normalize_observation, import_session, get_item_stats

    first = normalize_observation(_raw_question(external_id="q-1", prompt="Q1"))
    second_raw = _raw_question(external_id="q-2", prompt="Q2")
    second_raw["question"]["rank"] = "A"
    second_raw["correction"] = {
        "selected_answers": ["b"],
        "correct_answers": ["a"],
        "score_percent": 0,
        "is_correct": False,
        "displayed": True,
    }
    second = normalize_observation(second_raw)
    import_session({"external_session_id": "session-1", "session_date": "2026-08-10", "questions": [first, second]})

    assert get_item_stats("221") == {
        "attempts": 2,
        "correct": 1,
        "wrong": 1,
        "average_score_percent": 50.0,
        "rank_a": {"attempts": 1, "correct": 0, "wrong": 1},
        "rank_b": {"attempts": 1, "correct": 1, "wrong": 0},
    }


def test_local_capture_stop_contains_only_observed_corrections():
    from backend.core.ednpro.qcm_capture import normalize_observation
    from scripts.ednpro.qcm_capture_agent import CaptureBuffer

    buffer = CaptureBuffer()
    buffer.start("session-local")
    buffer.add(normalize_observation(_raw_question(external_id="q-1", prompt="Q1")))

    session = buffer.consume_stop() if (buffer.request_stop() is None) else None

    assert session is not None
    assert session["external_session_id"] == "session-local"
    assert [question["external_question_id"] for question in session["questions"]] == ["q-1"]
    assert buffer.status()["active"] is False


def test_import_can_publish_one_qcm_evaluation_per_item():
    from backend.core.ednpro.qcm_capture import import_session, normalize_observation, record_imported_evaluations
    from backend.core.reviews import local_store

    result = import_session({
        "external_session_id": "session-evaluation",
        "session_date": "2026-08-10",
        "questions": [normalize_observation(_raw_question(external_id="q-eval", prompt="Q"))],
    })
    persisted = record_imported_evaluations(
        session={"session_date": "2026-08-10"},
        result=result,
        course_resolver=lambda item: {"id": "course-221", "title": "Athérome"},
    )

    assert len(persisted) == 1
    assert local_store.get_qcm_sessions_by_course("course-221")[0]["platform"] == "EDNpro"
