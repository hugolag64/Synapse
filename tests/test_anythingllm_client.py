"""Tests unitaires — client HTTP AnythingLLM."""
import pytest
from unittest.mock import patch, MagicMock

from backend.core.lisa import anythingllm_client as client


@pytest.fixture(autouse=True)
def reset_cache():
    client.clear_workspace_cache()
    yield
    client.clear_workspace_cache()


def _mock_response(status_code: int, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        from requests import HTTPError
        resp.raise_for_status.side_effect = HTTPError(f"{status_code}")
    return resp


class TestListWorkspaces:
    def test_returns_workspace_list(self):
        payload = {"workspaces": [{"id": 1, "name": "Cardiologie", "slug": "cardiologie"}]}
        with patch("requests.get", return_value=_mock_response(200, payload)):
            result = client.list_workspaces()
        assert result == payload["workspaces"]

    def test_raises_on_connection_error(self):
        import requests
        with patch("requests.get", side_effect=requests.ConnectionError("refused")):
            with pytest.raises(client.AnythingLLMUnavailableError):
                client.list_workspaces()

    def test_raises_on_http_error(self):
        with patch("requests.get", return_value=_mock_response(500)):
            with pytest.raises(client.AnythingLLMUnavailableError):
                client.list_workspaces()

    def test_raises_on_non_json_response(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.side_effect = ValueError("not json")
        with patch("requests.get", return_value=resp):
            with pytest.raises(client.AnythingLLMUnavailableError):
                client.list_workspaces()

    def test_sends_bearer_header_when_api_key_set(self, monkeypatch):
        from backend.config.settings import settings
        monkeypatch.setattr(settings, "anythingllm_api_key", "secret-key")
        payload = {"workspaces": []}
        with patch("requests.get", return_value=_mock_response(200, payload)) as mock_get:
            client.list_workspaces()
        _, kwargs = mock_get.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer secret-key"


class TestResolveWorkspaceSlug:
    def test_matches_by_normalized_name(self):
        payload = {"workspaces": [
            {"id": 1, "name": "Cardiovasculaire", "slug": "cardiovasculaire-abcd"},
            {"id": 2, "name": "Dermatologie", "slug": "dermatologie-xyz"},
        ]}
        with patch("requests.get", return_value=_mock_response(200, payload)):
            slug = client.resolve_workspace_slug("Cardiovasculaire ❤️")
        assert slug == "cardiovasculaire-abcd"

    def test_caches_result_after_first_resolution(self):
        payload = {"workspaces": [{"id": 1, "name": "Cardiovasculaire", "slug": "cardio-slug"}]}
        with patch("requests.get", return_value=_mock_response(200, payload)) as mock_get:
            client.resolve_workspace_slug("Cardiovasculaire ❤️")
            client.resolve_workspace_slug("Cardiovasculaire ❤️")
        assert mock_get.call_count == 1

    def test_raises_when_no_match_above_threshold(self):
        payload = {"workspaces": [{"id": 1, "name": "Totalement autre chose", "slug": "autre"}]}
        with patch("requests.get", return_value=_mock_response(200, payload)):
            with pytest.raises(client.WorkspaceNotFoundError):
                client.resolve_workspace_slug("Cardiovasculaire ❤️")

    def test_raises_when_no_workspaces(self):
        payload = {"workspaces": []}
        with patch("requests.get", return_value=_mock_response(200, payload)):
            with pytest.raises(client.WorkspaceNotFoundError):
                client.resolve_workspace_slug("Cardiovasculaire ❤️")

    def test_matches_via_college_mapping_when_names_diverge(self):
        payload = {"workspaces": [{"id": 1, "name": "Cancérologie", "slug": "cancero-slug"}]}
        with patch("requests.get", return_value=_mock_response(200, payload)):
            slug = client.resolve_workspace_slug("Oncologie 🧬")
        assert slug == "cancero-slug"
