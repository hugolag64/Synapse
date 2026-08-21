import datetime

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    from backend.core.reviews import local_store
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "conf-analysis.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield local_store
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def _make_conference(local_store):
    return local_store.upsert_conference(
        date=datetime.date(2026, 9, 1),
        theme_raw="Cardiologie",
        match_status="matched",
        college_name="Cardiologie",
        source_file="planning.xlsx",
    )


def test_set_conference_audio_stores_path_and_hash(isolated_db):
    _, conf = _make_conference(isolated_db)
    updated = isolated_db.set_conference_audio(
        conf["id"], audio_path="data/conferences/audio/1.mp3", audio_hash="abc123"
    )
    assert updated["audio_path"] == "data/conferences/audio/1.mp3"
    assert updated["audio_hash"] == "abc123"
    assert updated["audio_uploaded_at"]


def test_create_conference_analysis_job_is_idempotent(isolated_db):
    _, conf = _make_conference(isolated_db)
    now = isolated_db._now()
    with isolated_db._conn() as con:
        con.execute(
            "INSERT INTO uness_annales (id, source_url, collected_at, faculte, niveau, titre, type_annale, created_at) "
            "VALUES (42, 'https://uness.example/42', ?, 'F', 'DFASM1', 'Titre', 'annale', ?)", (now, now),
        )
    job1 = isolated_db.create_conference_analysis_job(
        conference_id=conf["id"], uness_session_id=42, model_id="gemini-flash",
        idempotency_key="key-1", prompt_version="v1",
    )
    job2 = isolated_db.create_conference_analysis_job(
        conference_id=conf["id"], uness_session_id=42, model_id="gemini-flash",
        idempotency_key="key-1", prompt_version="v1",
    )
    assert job1["id"] == job2["id"]
    assert job1["status"] == "pending"


def test_list_uness_annale_questions_for_analysis(isolated_db):
    now = isolated_db._now()
    with isolated_db._conn() as con:
        con.execute(
            "INSERT INTO uness_annales (id, source_url, collected_at, faculte, niveau, titre, type_annale, created_at) "
            "VALUES (77, 'https://uness.example/77', ?, 'F', 'DFASM1', 'Titre', 'annale', ?)", (now, now),
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
    result = isolated_db.list_uness_annale_questions_for_analysis(77)
    assert result == [{"question_id": 1, "prompt": "Enonce", "answer": "Reponse", "official_item": "", "official_rank": ""}]


def test_retry_conference_analysis_job_creates_new_row_without_mutating_old(isolated_db):
    _, conf = _make_conference(isolated_db)
    now = isolated_db._now()
    with isolated_db._conn() as con:
        con.execute(
            "INSERT INTO uness_annales (id, source_url, collected_at, faculte, niveau, titre, type_annale, created_at) "
            "VALUES (55, 'https://uness.example/55', ?, 'F', 'DFASM1', 'Titre', 'annale', ?)", (now, now),
        )
    job = isolated_db.create_conference_analysis_job(
        conference_id=conf["id"], uness_session_id=55, model_id="gemini-flash",
        idempotency_key="hash-x:key", prompt_version="v1",
    )
    isolated_db.fail_conference_analysis_job(job["id"], error="quota")

    retried = isolated_db.retry_conference_analysis_job(job["id"])

    assert retried["id"] != job["id"]
    assert retried["status"] == "pending"
    old = isolated_db.get_conference_analysis_job(job["id"])
    assert old["status"] == "failed"  # jamais muté


def test_list_linked_conferences_with_analysis_status(isolated_db):
    _, conf = _make_conference(isolated_db)
    isolated_db.set_conference_uness_session(conf["id"], 77)
    rows = isolated_db.list_linked_conferences_with_analysis_status()
    assert len(rows) == 1
    assert rows[0]["analysis_status"] is None
