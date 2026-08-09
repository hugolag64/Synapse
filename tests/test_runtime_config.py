import pytest
from fastapi.testclient import TestClient
from nicegui import app

from backend.config.runtime import get_runtime_config


def test_runtime_defaults_to_local_development(monkeypatch):
    monkeypatch.delenv("SYNAPSE_ENV", raising=False)
    monkeypatch.delenv("SYNAPSE_HOST", raising=False)
    monkeypatch.delenv("SYNAPSE_PORT", raising=False)

    config = get_runtime_config()

    assert config.prod is False
    assert config.host == "127.0.0.1"
    assert config.port == 8082


def test_runtime_prod_defaults_to_container_listener(monkeypatch):
    monkeypatch.setenv("SYNAPSE_ENV", "prod")
    monkeypatch.delenv("SYNAPSE_HOST", raising=False)
    monkeypatch.delenv("SYNAPSE_PORT", raising=False)

    config = get_runtime_config()

    assert config.prod is True
    assert config.host == "0.0.0.0"
    assert config.port == 8000


def test_runtime_accepts_explicit_host_and_port(monkeypatch):
    monkeypatch.setenv("SYNAPSE_ENV", "prod")
    monkeypatch.setenv("SYNAPSE_HOST", "127.0.0.1")
    monkeypatch.setenv("SYNAPSE_PORT", "9123")

    config = get_runtime_config()

    assert (config.host, config.port) == ("127.0.0.1", 9123)


@pytest.mark.parametrize("value", ["0", "65536", "not-a-port"])
def test_runtime_rejects_invalid_ports(monkeypatch, value):
    monkeypatch.setenv("SYNAPSE_PORT", value)

    with pytest.raises(ValueError, match="SYNAPSE_PORT"):
        get_runtime_config()


def test_healthz_is_available_without_waiting_for_preload():
    import main  # noqa: F401  # registers the application routes

    response = TestClient(app).get("/api/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
