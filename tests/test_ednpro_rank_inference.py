from dataclasses import dataclass

import pytest


@pytest.fixture
def isolated_rank_db(tmp_path, monkeypatch):
    from backend.core.reviews import local_store

    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "rank.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield local_store
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


@dataclass(frozen=True)
class FakeQuestion:
    external_question_id: str
    item_number: str
    prompt: str = "Question"
    rank: str = ""


def fake_question(
    question_id: str,
    item_number: str,
    *,
    rank: str = "",
    prompt: str = "Question",
) -> FakeQuestion:
    return FakeQuestion(question_id, item_number, prompt=prompt, rank=rank)


def test_groups_only_questions_without_official_rank_by_item():
    from backend.core.ednpro.rank_inference import group_missing_rank_questions

    questions = (
        fake_question("q1", "233"),
        fake_question("q2", "233", rank="B"),
        fake_question("q3", "75"),
        fake_question("q4", ""),
    )

    assert group_missing_rank_questions(questions) == {
        "233": (questions[0],),
        "75": (questions[2],),
    }


def test_prompt_contains_oics_once_and_all_missing_questions():
    from backend.core.ednpro.rank_inference import build_rank_inference_prompt

    prompt = build_rank_inference_prompt(
        "233",
        (fake_question("q1", "233", prompt="Question 1"), fake_question("q2", "233", prompt="Question 2")),
        (
            {"code": "OIC-1", "intitule": "OIC A", "rang": "A"},
            {"code": "OIC-2", "intitule": "OIC B", "rang": "B"},
        ),
    )

    assert prompt.count("OIC-1") == 1
    assert prompt.count("OIC-2") == 1
    assert "Question 1" in prompt
    assert "Question 2" in prompt
    assert '"rank":"A|B|null"' in prompt


def test_parser_rejects_threshold_boundary_and_unknown_rank():
    from backend.core.ednpro.rank_inference import parse_rank_inference_response

    result = parse_rank_inference_response(
        '{"questions":['
        '{"id":"q1","rank":"A","confidence":0.850}'
        ',{"id":"q2","rank":"B","confidence":0.91,"oic_codes":["OIC-2"],"rationale":"detail"}'
        ',{"id":"q3","rank":"C","confidence":0.99}'
        ']}'
        ,
        ("q1", "q2", "q3"),
    )

    assert "q1" not in result
    assert result["q2"].rank == "B"
    assert result["q2"].confidence == pytest.approx(0.91)
    assert result["q2"].oic_codes == ("OIC-2",)
    assert "q3" not in result


def test_parser_ignores_unknown_question_ids_and_malformed_payload():
    from backend.core.ednpro.rank_inference import parse_rank_inference_response

    assert parse_rank_inference_response(
        '{"questions":[{"id":"unknown","rank":"A","confidence":0.99}]}',
        ("q1",),
    ) == {}
    assert parse_rank_inference_response("not-json", ("q1",)) == {}


def test_oics_are_deduplicated_across_college_aliases(isolated_rank_db):
    isolated_rank_db.upsert_lisa_oic(
        "course-a",
        [{"oic_code": "OIC-1", "intitule": "OIC A", "rang": "A"}],
    )
    isolated_rank_db.upsert_lisa_oic(
        "course-b",
        [
            {"oic_code": "OIC-1", "intitule": "OIC A", "rang": "A"},
            {"oic_code": "OIC-2", "intitule": "OIC B", "rang": "B"},
        ],
    )

    rows = isolated_rank_db.get_lisa_oic_for_item("233", ["course-a", "course-b"])

    assert [row["code"] for row in rows] == ["OIC-1", "OIC-2"]
    assert [row["rang"] for row in rows] == ["A", "B"]


def test_dom_rank_is_marked_as_official():
    from backend.core.ednpro.qcm_capture import extract_corrected_observation

    observation = extract_corrected_observation(
        """
        <article data-qcm-question="q-dom" data-item-number="233" data-corrected="true">
          <span>Item 233 · QCM · Rang B</span>
          <h3 data-question-stem>Question visible</h3>
          <label data-choice-id="a" data-selected="true" data-correct="true">A</label>
          <div data-explanation-simple>Correction</div>
        </article>
        """
    )

    assert observation is not None
    assert observation.rank == "B"
    assert observation.rank_source == "ednpro"
    assert observation.rank_confidence == 1.0


def test_import_persists_rank_provenance_for_question_and_attempt(isolated_rank_db):
    from backend.core.ednpro.qcm_capture import EdnproQuestionObservation, import_session

    import_session(
        {
            "external_session_id": "session-provenance",
            "session_date": "2026-08-10",
            "questions": [
                EdnproQuestionObservation(
                    external_question_id="q-provenance",
                    item_number="233",
                    prompt="Question",
                    rank="A",
                    rank_source="gemini",
                    rank_confidence=0.91,
                    rank_evidence=("OIC-1",),
                    corrected=True,
                )
            ],
        }
    )

    with isolated_rank_db._conn() as con:
        question = con.execute(
            "SELECT rank, rank_source, rank_confidence, rank_evidence_json FROM ednpro_qcm_questions"
        ).fetchone()
        attempt = con.execute(
            "SELECT rank, rank_source, rank_confidence, rank_evidence_json FROM ednpro_qcm_attempts"
        ).fetchone()

    assert question["rank"] == "A"
    assert question["rank_source"] == "gemini"
    assert question["rank_confidence"] == pytest.approx(0.91)
    assert question["rank_evidence_json"] == '["OIC-1"]'
    assert attempt["rank"] == "A"
    assert attempt["rank_source"] == "gemini"


def test_enrich_session_calls_gemini_once_per_item_and_preserves_official_rank(monkeypatch):
    from unittest.mock import Mock

    from backend.core.ai.routing import AIModel, AIResponse
    from backend.core.ednpro.qcm_capture import enrich_session_ranks

    class Course:
        def __init__(self, course_id, item_number):
            self.id = course_id
            self.item_number = item_number

    monkeypatch.setattr(
        "backend.core.reviews.local_store.get_lisa_oic_for_item",
        lambda item_number, course_ids: [{"code": "OIC-1", "intitule": "OIC A", "rang": "A"}],
    )
    service = Mock()
    service.generate.return_value = AIResponse(
        '{"questions":[{"id":"q1","rank":"A","confidence":0.91,"oic_codes":["OIC-1"]},'
        '{"id":"q2","rank":"B","confidence":0.84,"oic_codes":["OIC-1"]}]}',
        AIModel.FLASH_LITE,
    )
    session = {
        "external_session_id": "session-enrichment",
        "questions": [
            {"external_question_id": "q1", "item_number": "233", "prompt": "Q1", "corrected": True},
            {"external_question_id": "q2", "item_number": "233", "prompt": "Q2", "corrected": True},
            {"external_question_id": "q3", "item_number": "233", "prompt": "Q3", "rank": "B", "corrected": True},
        ],
    }

    enriched = enrich_session_ranks(
        session,
        courses=[Course("course-233", "233")],
        service=service,
    )

    assert service.generate.call_count == 1
    prompt = service.generate.call_args.args[1]
    assert prompt.count("OIC-1") == 1
    by_id = {row["external_question_id"]: row for row in enriched["questions"]}
    assert by_id["q1"]["rank"] == "A"
    assert by_id["q1"]["rank_source"] == "gemini"
    assert by_id["q2"]["rank"] == ""
    assert by_id["q3"]["rank"] == "B"
    assert by_id["q3"]["rank_source"] == "ednpro"
