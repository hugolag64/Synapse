"""Tests unitaires du contrat LiSA MediaWiki API."""

from unittest.mock import MagicMock, patch

import pytest


def _mock_response(status_code: int, payload=None, json_error: Exception | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.raise_for_status = MagicMock()
    if status_code >= 400:
        from requests import HTTPError

        response.raise_for_status.side_effect = HTTPError(str(status_code))
    if json_error:
        response.json.side_effect = json_error
    else:
        response.json.return_value = payload
    return response


_VALID_API = {
    "query": {
        "pages": {
            "1": {
                "pageid": 1,
                "title": "OIC-223-01-A",
                "revisions": [{"*": "#REDIRECT [[Connaître le risque cardiovasculaire global OIC-223-01-A]]"}],
            },
            "2": {
                "pageid": 2,
                "title": "OIC-223-02-A",
                "revisions": [{"*": "#REDIRECT [[Connaître les trois grands types de dyslipidémies OIC-223-02-A]]"}],
            },
            "3": {
                "pageid": 3,
                "title": "OIC-223-03-B",
                "revisions": [{"*": "#REDIRECT [[Connaître les relations entre dyslipidémies et athérosclérose OIC-223-03-B]]"}],
            },
        }
    }
}


class TestScrapeOic:
    def test_parses_valid_mediawiki_response(self):
        from backend.core.lisa.scraper import scrape_oic

        with patch("requests.get", return_value=_mock_response(200, _VALID_API)):
            result = scrape_oic("Dyslipidémies", "223")

        assert len(result) == 3
        assert [row["rang"] for row in result] == ["A", "A", "B"]

    def test_oic_fields_correct(self):
        from backend.core.lisa.scraper import scrape_oic

        with patch("requests.get", return_value=_mock_response(200, _VALID_API)):
            first = scrape_oic("Dyslipidémies", "223")[0]

        assert first["oic_code"] == "OIC-223-01-A"
        assert "OIC-223-01-A" not in first["intitule"]
        assert first["intitule"] == "Connaître le risque cardiovasculaire global"
        assert first["ordre"] == 1

    def test_empty_pages_returns_empty_list(self):
        from backend.core.lisa.scraper import scrape_oic

        with patch("requests.get", return_value=_mock_response(200, {"query": {"pages": {}}})):
            assert scrape_oic("Cours inconnu", "999") == []

    def test_http_error_raises_lisa_fetch_error(self):
        from backend.core.lisa.scraper import LisaFetchError, scrape_oic

        with patch("requests.get", return_value=_mock_response(404)):
            with pytest.raises(LisaFetchError, match="Erreur réseau LiSA"):
                scrape_oic("Cours inconnu", "999")

    def test_invalid_json_raises_lisa_fetch_error(self):
        from backend.core.lisa.scraper import LisaFetchError, scrape_oic

        with patch(
            "requests.get",
            return_value=_mock_response(200, json_error=ValueError("not json")),
        ):
            with pytest.raises(LisaFetchError, match="non-JSON"):
                scrape_oic("Dyslipidémies", "223")

    def test_request_uses_item_prefix_and_api_endpoint(self):
        from backend.core.lisa.scraper import scrape_oic

        captured = {}

        def fake_get(url, **kwargs):
            captured["url"] = url
            captured["params"] = kwargs["params"]
            return _mock_response(200, {"query": {"pages": {}}})

        with patch("requests.get", side_effect=fake_get):
            scrape_oic("Titre ignoré", "232")

        assert captured["url"].endswith("/api.php")
        assert captured["params"]["gapprefix"] == "OIC-232-"

    def test_network_error_raises_lisa_fetch_error(self):
        from backend.core.lisa.scraper import LisaFetchError, scrape_oic
        import requests

        with patch("requests.get", side_effect=requests.ConnectionError("timeout")):
            with pytest.raises(LisaFetchError):
                scrape_oic("Dyslipidémies", "223")
