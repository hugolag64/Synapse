from pathlib import Path


def test_pytest_uses_database_outside_project_tree():
    from backend.core.reviews import local_store

    project_db = Path(__file__).resolve().parents[1] / "data" / "synapse_local.db"
    assert local_store.DB_PATH.resolve() != project_db.resolve()


def test_gemini_error_redaction_hides_query_api_key():
    from backend.core.ai.gemini_client import _redact_provider_secrets

    redacted = _redact_provider_secrets(
        "429 url=https://example.test/generate?key=secret-value&foo=bar"
    )

    assert "secret-value" not in redacted
    assert "key=***" in redacted
