import json

from backend.core.ai.batch_client import UploadedFile
from backend.core.conferences.analysis_prompt import (
    ConferenceQuestionSnapshot,
    build_conference_analysis_request,
    parse_conference_analysis_response,
)


def test_build_conference_analysis_request_includes_audio_and_snapshot():
    audio = UploadedFile(uri="files/abc", name="files/abc", mime_type="audio/mpeg")
    questions = [
        ConferenceQuestionSnapshot(
            question_id="q1", enonce="Quel est le traitement de première intention ?",
            official_answer="Bêtabloquant", official_item="", official_rank="",
        )
    ]
    body = build_conference_analysis_request(
        audio_file=audio, college_label="Cardiologie", questions=questions,
    )
    contents = body["batch"]["input_config"]["requests"]["requests"][0]["request"]["contents"]
    parts = contents[0]["parts"]
    assert {"file_data": {"mime_type": "audio/mpeg", "file_uri": "files/abc"}} in parts
    assert any("q1" in part.get("text", "") for part in parts)


def test_parse_conference_analysis_response_keeps_only_candidate_items():
    raw = json.dumps({
        "summary": "Cours sur l'insuffisance cardiaque.",
        "questions": [
            {
                "question_id": "q1", "item_numbers": ["ITEM 232"], "item_confidence": 0.9,
                "item_rationale": "cité explicitement",
                "rank": "A", "rank_confidence": 0.9, "rank_rationale": "cours de rang A",
                "verdict": "concordant", "verdict_confidence": 0.8,
                "verdict_rationale": "le professeur confirme la réponse",
                "transcript_excerpt": "00:12:30 - ...",
            },
            {
                "question_id": "q2", "item_numbers": ["ITEM 999"], "item_confidence": 0.95,
                "item_rationale": "hors référentiel",
                "rank": "B", "rank_confidence": 0.9, "rank_rationale": "",
                "verdict": "incertain", "verdict_confidence": 0.4, "verdict_rationale": "",
                "transcript_excerpt": "",
            },
        ],
    })
    result = parse_conference_analysis_response(
        raw,
        known_question_ids={"q1", "q2"},
        candidate_items={"q1": {"ITEM 232", "ITEM 233"}, "q2": {"ITEM 1"}},
    )
    assert result.summary == "Cours sur l'insuffisance cardiaque."
    assert result.questions["q1"].item_number == "ITEM 232"
    # q2 : item proposé hors liste candidate -> rejeté, jamais inventé
    assert result.questions["q2"].item_number == ""
    assert result.questions["q2"].item_needs_admin is True


def test_parse_conference_analysis_response_ignores_unknown_question_ids():
    raw = json.dumps({"summary": "", "questions": [
        {"question_id": "ghost", "item_numbers": [], "item_confidence": 0, "item_rationale": "",
         "rank": "", "rank_confidence": 0, "rank_rationale": "",
         "verdict": "incertain", "verdict_confidence": 0, "verdict_rationale": "", "transcript_excerpt": ""},
    ]})
    result = parse_conference_analysis_response(raw, known_question_ids={"q1"}, candidate_items={"q1": set()})
    assert result.questions == {}
