"""Tests unitaires — helpers de payload Notion."""
import pytest
import datetime
from backend.core.notion.payloads import (
    checkbox, number, notion_date, url_prop, relation, select, rich_text
)
from backend.config.settings import NOTION_PROPS as P


class TestCheckbox:
    def test_true(self):
        assert checkbox(True) == {"checkbox": True}

    def test_false(self):
        assert checkbox(False) == {"checkbox": False}

    def test_coerces_truthy(self):
        assert checkbox(1)["checkbox"] is True

    def test_coerces_falsy(self):
        assert checkbox(0)["checkbox"] is False


class TestNumber:
    def test_integer(self):
        assert number(3) == {"number": 3}

    def test_float(self):
        assert number(3.5) == {"number": 3.5}

    def test_zero(self):
        assert number(0) == {"number": 0}


class TestNotionDate:
    def test_iso_format(self):
        result = notion_date("2026-05-23")
        assert result == {"date": {"start": "2026-05-23"}}

    def test_key_structure(self):
        result = notion_date("2026-01-01")
        assert "date" in result
        assert "start" in result["date"]


class TestUrlProp:
    def test_url(self):
        assert url_prop("https://example.com") == {"url": "https://example.com"}

    def test_none(self):
        assert url_prop(None) == {"url": None}


class TestRelation:
    def test_single_id(self):
        result = relation(["abc-123"])
        assert result == {"relation": [{"id": "abc-123"}]}

    def test_multiple_ids(self):
        result = relation(["a", "b"])
        assert len(result["relation"]) == 2

    def test_empty(self):
        assert relation([]) == {"relation": []}


class TestNotionPropsConstants:
    """Vérifie que les constantes critiques ont les bonnes valeurs (sans accent)."""

    def test_nb_lectures_college_no_accent(self):
        assert P.NB_LECTURES_COLLEGE == "Nombre lecture college"

    def test_nb_lectures_ue(self):
        assert P.NB_LECTURES_UE == "Nombre lecture"

    def test_rappel_college_with_accent(self):
        # "collège" avec accent — confirmé Notion
        assert "collège" in P.RAPPEL_COLLEGE

    def test_url_pdf_college_all_caps(self):
        assert P.URL_PDF_COLLEGE == "URL PDF COLLEGE"

    def test_url_pdf_ue(self):
        assert P.URL_PDF_UE == "URL PDF"
