"""Tests unitaires — LiSA OIC scraper."""
import pytest
from unittest.mock import patch, MagicMock


_VALID_HTML = """
<html><body>
<table>
  <tr>
    <th>Intitulé</th><th>Rang</th><th>Rubrique</th><th>Ordre</th>
  </tr>
  <tr>
    <td><a href="#">Connaître l'évaluation du risque cardiovasculaire global OIC-223-01-A</a></td>
    <td>A</td><td>Définition</td><td>1</td>
  </tr>
  <tr>
    <td><a href="#">Connaître les trois grands types de dyslipidémies OIC-223-02-A</a></td>
    <td>A</td><td>Définition</td><td>2</td>
  </tr>
  <tr>
    <td><a href="#">Connaître les relations entre dyslipidémies et athérosclérose OIC-223-03-B</a></td>
    <td>B</td><td>Physiopathologie</td><td>3</td>
  </tr>
</table>
</body></html>
"""

_NO_TABLE_HTML = "<html><body><p>Aucun contenu</p></body></html>"


def _mock_response(status_code: int, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        from requests import HTTPError
        resp.raise_for_status.side_effect = HTTPError(f"{status_code}")
    return resp


class TestScrapeOic:
    def test_parses_valid_html(self):
        from backend.core.lisa.scraper import scrape_oic
        with patch("requests.get", return_value=_mock_response(200, _VALID_HTML)):
            result = scrape_oic("Dyslipidémies", "223")

        assert len(result) == 3
        a_oics = [r for r in result if r["rang"] == "A"]
        b_oics = [r for r in result if r["rang"] == "B"]
        assert len(a_oics) == 2
        assert len(b_oics) == 1

    def test_oic_fields_correct(self):
        from backend.core.lisa.scraper import scrape_oic
        with patch("requests.get", return_value=_mock_response(200, _VALID_HTML)):
            result = scrape_oic("Dyslipidémies", "223")

        first = result[0]
        assert first["oic_code"] == "OIC-223-01-A"
        assert "OIC-223-01-A" not in first["intitule"]   # code supprimé du titre
        assert "évaluation du risque" in first["intitule"]
        assert first["rang"] == "A"
        assert first["rubrique"] == "Définition"
        assert first["ordre"] == 1

    def test_returns_empty_on_404(self):
        from backend.core.lisa.scraper import scrape_oic
        with patch("requests.get", return_value=_mock_response(404)):
            result = scrape_oic("CoursInconnu", "999")
        assert result == []

    def test_returns_empty_when_no_table(self):
        from backend.core.lisa.scraper import scrape_oic
        with patch("requests.get", return_value=_mock_response(200, _NO_TABLE_HTML)):
            result = scrape_oic("Dyslipidémies", "223")
        assert result == []

    def test_raises_on_network_error(self):
        from backend.core.lisa.scraper import scrape_oic, LisaFetchError
        import requests
        with patch("requests.get", side_effect=requests.ConnectionError("timeout")):
            with pytest.raises(LisaFetchError):
                scrape_oic("Dyslipidémies", "223")

    def test_url_built_from_title(self):
        from backend.core.lisa.scraper import scrape_oic
        captured = {}
        def fake_get(url, **kwargs):
            captured["url"] = url
            return _mock_response(200, _NO_TABLE_HTML)
        with patch("requests.get", side_effect=fake_get):
            scrape_oic("Insuffisance cardiaque", "232")
        assert "Insuffisance_cardiaque" in captured["url"]
        assert "livret.uness.fr/lisa/2026/" in captured["url"]
