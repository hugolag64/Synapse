import datetime
import json
from unittest.mock import Mock

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    from backend.core.reviews import local_store
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "job-runner.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield local_store
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def _seed_conference_with_dossier(local_store, *, with_audio=True):
    now = local_store._now()
    with local_store._conn() as con:
        con.execute(
            "INSERT INTO uness_annales (id, source_url, faculte, niveau, annee, matiere, titre, type_annale, collected_at, created_at) "
            "VALUES (77, 'https://uness.example/77', 'F', 'DFASM1', 2026, 'Cardiologie', 'Titre', 'annale', ?, ?)", (now, now),
        )
        con.execute(
            "INSERT INTO ai_practice_questions (id, practice_kind, question_kind, position, prompt, answer, explanation, question_hash, created_at) "
            "VALUES (1, 'QCM', 'CLOSED', 1, 'Enonce', 'Reponse', '', 'hash1', ?)", (now,),
        )
        con.execute(
            "INSERT INTO ai_practice_sessions (id, practice_kind, total_questions, annale_id, created_at) "
            "VALUES (1, 'QCM', 1, 77, ?)", (now,),
        )
        con.execute("INSERT INTO ai_practice_session_questions (session_id, question_id, position) VALUES (1, 1, 1)")
    _, conf = local_store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="Cardiologie", match_status="matched",
        college_name="Cardiologie", source_file="planning.xlsx",
    )
    local_store.set_conference_uness_session(conf["id"], 77)
    if with_audio:
        local_store.set_conference_audio(conf["id"], audio_path="data/conferences/audio/1.mp3", audio_hash="hash-abc")
    return local_store.get_conference(conf["id"])


def test_scan_creates_one_pending_job_per_eligible_conference(isolated_db):
    from backend.core.conferences import analysis_job_runner
    _seed_conference_with_dossier(isolated_db)
    created = analysis_job_runner.scan_and_queue_conference_analyses()
    assert created == 1
    jobs = isolated_db.list_conference_analysis_jobs_due_for_poll(limit=10)
    assert jobs == []  # still pending, not yet submitted/polled


def test_scan_skips_conference_without_audio(isolated_db):
    from backend.core.conferences import analysis_job_runner
    _seed_conference_with_dossier(isolated_db, with_audio=False)
    assert analysis_job_runner.scan_and_queue_conference_analyses() == 0


def test_submit_pending_jobs_uploads_audio_and_creates_batch_job(tmp_path, isolated_db):
    from backend.core.conferences import analysis_job_runner
    from backend.core.ai.batch_client import UploadedFile, BatchJobHandle

    conf = _seed_conference_with_dossier(isolated_db)
    audio_path = tmp_path / "1.mp3"
    audio_path.write_bytes(b"fake")
    isolated_db.set_conference_audio(conf["id"], audio_path=str(audio_path), audio_hash="hash-abc")
    analysis_job_runner.scan_and_queue_conference_analyses()

    client = Mock()
    client.upload_audio_file.return_value = UploadedFile(uri="files/abc", name="files/abc", mime_type="audio/mpeg")
    client.create_batch_job.return_value = BatchJobHandle(name="batches/job-1")

    counts = analysis_job_runner.submit_pending_conference_analysis_jobs(client=client)

    assert counts["submitted"] == 1
    client.upload_audio_file.assert_called_once()
    client.create_batch_job.assert_called_once()
    with isolated_db._conn() as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM conference_analysis_jobs").fetchall()]
    assert len(rows) == 1
    assert rows[0]["status"] == "submitted"
    assert rows[0]["provider_job_name"] == "batches/job-1"


def test_poll_applies_result_without_overwriting_anything_official(isolated_db, monkeypatch):
    from backend.core.conferences import analysis_job_runner
    from backend.core.ai.batch_client import BatchJobStatus

    conf = _seed_conference_with_dossier(isolated_db)
    job = isolated_db.create_conference_analysis_job(
        conference_id=conf["id"], uness_session_id=77, model_id="gemini-flash",
        idempotency_key="hash-abc:key", prompt_version="v1",
    )
    isolated_db.mark_conference_analysis_job_submitted(job["id"], provider_job_name="batches/job-1", next_poll_at=isolated_db._now())

    response_payload = {
        "summary": "Résumé de la conférence.",
        "questions": [{
            "question_id": "1", "item_numbers": ["ITEM 232"], "item_confidence": 0.9,
            "item_rationale": "cité", "rank": "A", "rank_confidence": 0.9, "rank_rationale": "rang A",
            "verdict": "concordant", "verdict_confidence": 0.9, "verdict_rationale": "confirmé",
            "transcript_excerpt": "00:05:00",
        }],
    }
    client = Mock()
    client.get_batch_job.return_value = BatchJobStatus(
        name="batches/job-1", done=True, state="JOB_STATE_SUCCEEDED",
        inlined_responses=[{"response": {"candidates": [{"content": {"parts": [{"text": json.dumps(response_payload)}]}}]}}],
        responses_file_name=None, error=None,
    )
    monkeypatch.setattr(
        "backend.core.conferences.analysis_job_runner.candidate_items_for_college",
        lambda label: [{"item": "ITEM 232"}],
    )

    counts = analysis_job_runner.poll_running_conference_analysis_jobs(client=client)

    assert counts["succeeded"] == 1
    updated_job = isolated_db.get_conference_analysis_job(job["id"])
    assert updated_job["status"] == "succeeded"
    items = isolated_db.get_ai_practice_question_items(1)
    assert items[0]["item_number"] == "ITEM 232"
    assert items[0]["source"] == "gemini_conference"
    with isolated_db._conn() as con:
        usage_rows = con.execute("SELECT task, model, context FROM ai_usage_logs").fetchall()
    assert usage_rows[0]["task"] == "conference_analysis"
    assert "batch" in usage_rows[0]["context"]
