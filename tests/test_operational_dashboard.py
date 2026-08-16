import json
import uuid

from backend.core.practice import PracticeDifficulty, PracticeKind, PracticeSessionSpec
from backend.core.qcm.operational_dashboard import (
    get_discordance_profile,
    get_frequency_coverage,
    get_rank_a_security,
    get_replay_curve,
    get_rhythm_profile,
)
from backend.core.reviews import local_store


def _suffix() -> str:
    return uuid.uuid4().hex[:10]


def test_rank_a_security_uses_official_ednpro_answers_only():
    local_store.init_db()
    item = f"DASH-RANK-{_suffix()}"
    with local_store._conn() as con:
        con.execute(
            "INSERT INTO ednpro_qcm_sessions (external_session_id, session_date, created_at, imported_at) VALUES (?, ?, ?, ?)",
            (f"session-{item}", "2026-08-16", "2026-08-16", "2026-08-16"),
        )
        session_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.execute(
            """INSERT INTO ednpro_qcm_questions
               (external_question_id, item_number, prompt, choices_json, correct_answers_json,
                rank, rank_source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'A', 'ednpro', ?, ?)""",
            (f"question-{item}", item, "Prompt", "[]", json.dumps(["A"]), "2026-08-16", "2026-08-16"),
        )
        question_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.execute(
            """INSERT INTO ednpro_qcm_attempts
               (session_id, question_id, selected_answers_json, is_correct, score_percent,
                rank, rank_source, answered_at)
               VALUES (?, ?, ?, 1, 100, 'A', 'ednpro', ?)""",
            (session_id, question_id, json.dumps(["A"]), "2026-08-16"),
        )

    result = get_rank_a_security()

    assert result["available"] is True
    assert result["percent"] == 100.0
    assert result["items"][0]["item_number"] == item


def test_operational_profiles_expose_discordance_rhythm_coverage_and_replay():
    local_store.init_db()
    item = f"DASH-COVERAGE-{_suffix()}"
    spec = PracticeSessionSpec(
        practice_kind=PracticeKind.QCM,
        total_questions=1,
        closed_questions=1,
        item_number=item,
        difficulty=PracticeDifficulty.EDN,
    )
    session_id = local_store.create_ai_practice_session(
        spec=spec,
        questions=[{
            "prompt": "Prompt",
            "kind": "closed",
            "choices": ["A", "B"],
            "answer": "A",
            "explanation": "Explication",
        }],
        model="test",
    )
    question_id = local_store.get_ai_practice_session(session_id)[0]["id"]
    attempt_id = local_store.record_ai_practice_attempt(
        session_id=session_id,
        question_id=question_id,
        response='["A"]',
        score_percent=50,
        is_correct=False,
        duration_seconds=240,
        finalize_session=False,
    )
    local_store.replace_ai_practice_attempt_propositions(attempt_id, [
        {"proposition_id": "A", "selected": False, "expected": True, "discordance": "omission"},
        {"proposition_id": "B", "selected": True, "expected": False, "discordance": "exces"},
    ])
    with local_store._conn() as con:
        con.execute(
            "UPDATE ai_practice_sessions SET score_percent = 50, completed_at = '2026-08-10T10:00:00' WHERE id = ?",
            (session_id,),
        )
    replay_id = local_store.replay_ai_practice_session(session_id)
    replay_question_id = local_store.get_ai_practice_session(replay_id)[0]["id"]
    local_store.record_ai_practice_attempt(
        session_id=replay_id,
        question_id=replay_question_id,
        response='["A"]',
        score_percent=100,
        is_correct=True,
        duration_seconds=120,
        finalize_session=False,
    )
    with local_store._conn() as con:
        con.execute(
            "UPDATE ai_practice_sessions SET score_percent = 100, completed_at = '2026-08-12T10:00:00' WHERE id = ?",
            (replay_id,),
        )
        con.execute(
            "INSERT INTO ednpro_item_frequency (item_number, priority, session_count, question_count, collected_at) VALUES (?, 'indispensable', 4, 12, ?)",
            (item, "2026-08-16"),
        )

    discordance = get_discordance_profile()
    rhythm = get_rhythm_profile()
    coverage = get_frequency_coverage()
    replay = get_replay_curve()

    assert discordance["omission"] >= 1
    assert discordance["exces"] >= 1
    assert any(row["format"] == "qcm" and row["questions"] >= 2 for row in rhythm["formats"])
    assert coverage["uncovered_count"] == 0
    assert replay["available"] is True
    assert len(replay["chains"][0]["points"]) == 2
