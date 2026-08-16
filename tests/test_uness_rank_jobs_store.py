import datetime as dt
import pytest

from backend.core.practice.models import PracticeKind, PracticeSessionSpec


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    from backend.core.reviews import local_store

    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "rank-jobs.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield local_store
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def _annale(store) -> int:
    return store.create_uness_annale(
        source_url="https://uness.example/annale/ranks",
        collected_at="2026-08-16T10:00:00+00:00",
        faculte="Faculté test",
        niveau="DFASM1",
        annee=2026,
        matiere="Médecine",
        titre="Annale test rangs",
        type_annale="matiere",
    )


def _session(store, annale_id: int, question_id: str, *, rank: str = "") -> int:
    metadata = {
        "uness": {
            "provenance": {"source": "UNESS"},
            "question": {
                "id": question_id,
                "rank": rank,
                "rank_source": "official" if rank else "unknown",
                "rank_confidence": 1.0 if rank else None,
                "rank_evidence": [],
                "item_numbers": ["233"],
            },
        }
    }
    spec = PracticeSessionSpec(
        practice_kind=PracticeKind.QCM,
        total_questions=1,
        closed_questions=1,
        item_number="233",
        item_numbers=("233",),
    )
    session_id = store.create_ai_practice_session(
        spec=spec,
        questions=[
            {
                "kind": "closed",
                "prompt": f"Question {question_id}",
                "choices": ["A", "B"],
                "answer": '["A"]',
                "explanation": "Correction officielle.",
                "import_metadata": metadata,
                "item_numbers": ("233",),
            }
        ],
        model="uness-verified-local",
    )
    store.set_session_annale_id(session_id, annale_id)
    return session_id


def test_scan_is_idempotent_and_skips_official_rank(isolated_db):
    annale_id = _annale(isolated_db)
    _session(isolated_db, annale_id, "q-missing")
    _session(isolated_db, annale_id, "q-official", rank="A")

    first = isolated_db.scan_uness_rank_jobs()
    second = isolated_db.scan_uness_rank_jobs()

    assert [job["question_external_id"] for job in first] == ["q-missing"]
    assert second == []
    assert isolated_db.list_uness_rank_jobs()[0]["status"] == "pending"


def test_claim_recovers_expired_lease(isolated_db):
    annale_id = _annale(isolated_db)
    _session(isolated_db, annale_id, "q-lease")
    isolated_db.scan_uness_rank_jobs()

    claimed = isolated_db.claim_uness_rank_jobs(limit=1, worker_id="worker-a")
    assert len(claimed) == 1
    assert isolated_db.claim_uness_rank_jobs(limit=1, worker_id="worker-b") == []

    old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat()
    with isolated_db._conn() as con:
        con.execute(
            "UPDATE uness_rank_inference_jobs SET locked_at = ? WHERE id = ?",
            (old, claimed[0]["id"]),
        )

    recovered = isolated_db.claim_uness_rank_jobs(limit=1, worker_id="worker-b")
    assert recovered[0]["id"] == claimed[0]["id"]
    assert recovered[0]["worker_id"] == "worker-b"


def test_result_and_admin_decision_update_only_rank_metadata(isolated_db):
    annale_id = _annale(isolated_db)
    session_id = _session(isolated_db, annale_id, "q-result")
    job = isolated_db.scan_uness_rank_jobs()[0]
    claimed = isolated_db.claim_uness_rank_jobs(limit=1, worker_id="worker-a")[0]

    isolated_db.record_uness_rank_result(
        claimed["id"],
        rank="A",
        confidence=0.92,
        ambiguous=False,
        oic_codes=["OIC-233-01-A"],
        rationale="OIC indispensable explicite.",
        raw_response='{"questions": []}',
        status="needs_admin",
    )
    accepted = isolated_db.accept_uness_rank_job(claimed["id"])

    assert accepted["status"] == "approved"
    question = isolated_db.get_ai_practice_session(session_id)[0]
    assert question["prompt"] == "Question q-result"
    assert question["answer"] == '["A"]'
    assert question["uness"]["question"]["rank"] == "A"
    assert question["uness"]["question"]["rank_source"] == "gemini"
    assert question["uness"]["question"]["rank_confidence"] == pytest.approx(0.92)
    assert question["uness"]["question"]["rank_evidence"] == ["OIC-233-01-A"]

    events = isolated_db.list_uness_rank_events(claimed["id"])
    assert [event["status"] for event in events] == ["pending", "running", "needs_admin", "approved"]


def test_manual_decision_requires_valid_rank_and_reason(isolated_db):
    annale_id = _annale(isolated_db)
    _session(isolated_db, annale_id, "q-manual")
    job = isolated_db.scan_uness_rank_jobs()[0]

    with pytest.raises(ValueError, match="rang"):
        isolated_db.decide_uness_rank_job(job["id"], rank="C", reason="Erreur")
    with pytest.raises(ValueError, match="raison"):
        isolated_db.decide_uness_rank_job(job["id"], rank="B", reason="")

    decided = isolated_db.decide_uness_rank_job(job["id"], rank="B", reason="Revue expert")
    assert decided["status"] == "approved"
    question = isolated_db.get_ai_practice_sessions_history(limit=1, exclude_uness=False)
    assert question
