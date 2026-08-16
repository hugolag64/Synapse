from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.api import qcm


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(qcm.router)
    return TestClient(app)


def test_list_rank_jobs_returns_filters_and_count(client, monkeypatch):
    jobs = [{"id": 7, "status": "needs_admin", "question_external_id": "q1"}]
    monkeypatch.setattr(qcm.local_store, "list_uness_rank_jobs", lambda **kwargs: jobs)

    response = client.get("/api/qcm/admin/rank-jobs", params={"status": "needs_admin", "limit": 20})

    assert response.status_code == 200
    assert response.json() == {"jobs": jobs, "count": 1}


def test_scan_rank_jobs_is_idempotent_at_api_boundary(client, monkeypatch):
    monkeypatch.setattr(qcm.local_store, "scan_uness_rank_jobs", lambda: [{"id": 1}, {"id": 2}])

    response = client.post("/api/qcm/admin/rank-jobs/scan")

    assert response.status_code == 200
    assert response.json() == {"created": 2, "jobs": [{"id": 1}, {"id": 2}]}


def test_accept_and_retry_return_updated_job(client, monkeypatch):
    monkeypatch.setattr(qcm.local_store, "accept_uness_rank_job", lambda job_id: {"id": job_id, "status": "approved"})
    monkeypatch.setattr(qcm.local_store, "retry_uness_rank_job", lambda job_id: {"id": job_id, "status": "pending"})

    accepted = client.post("/api/qcm/admin/rank-jobs/12/accept")
    retried = client.post("/api/qcm/admin/rank-jobs/12/retry")

    assert accepted.status_code == 200
    assert accepted.json() == {"id": 12, "status": "approved"}
    assert retried.status_code == 200
    assert retried.json() == {"id": 12, "status": "pending"}


def test_manual_decision_validates_rank_and_reason(client):
    invalid_rank = client.post(
        "/api/qcm/admin/rank-jobs/12/decide",
        json={"rank": "C", "reason": "Revue"},
    )
    missing_reason = client.post(
        "/api/qcm/admin/rank-jobs/12/decide",
        json={"rank": "A", "reason": ""},
    )

    assert invalid_rank.status_code == 422
    assert missing_reason.status_code == 422


def test_unknown_job_becomes_404_and_store_error_becomes_400(client, monkeypatch):
    monkeypatch.setattr(qcm.local_store, "accept_uness_rank_job", lambda job_id: None)
    assert client.post("/api/qcm/admin/rank-jobs/99/accept").status_code == 404

    def raise_value_error(job_id):
        raise ValueError("L'inférence Gemini est incertaine")

    monkeypatch.setattr(qcm.local_store, "accept_uness_rank_job", raise_value_error)
    response = client.post("/api/qcm/admin/rank-jobs/99/accept")
    assert response.status_code == 400
    assert "incertaine" in response.json()["detail"]
