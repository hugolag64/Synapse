"""Tests pour _find_course() dans ai_qcm/service.py"""
import pytest
from unittest.mock import patch
from types import SimpleNamespace
from backend.core.ai_qcm.service import _find_course


def _c(id_, title, item_number=""):
    return SimpleNamespace(id=id_, title=title, item_number=item_number)


class TestFindCourse:
    def test_single_match_by_item(self):
        courses = [_c("a", "Arrêt cardio-circulatoire", "331"), _c("b", "Dyslipidémies", "223")]
        cid, title, item = _find_course("331", "", courses)
        assert cid == "a"

    def test_no_match_returns_empty(self):
        courses = [_c("a", "Arrêt cardio-circulatoire", "331")]
        cid, title, item = _find_course("999", "Inconnu", courses)
        assert cid == ""

    def test_multi_match_item_prefers_canonical(self):
        """Quand deux cours ont même item_number, choisir le plus canonique."""
        courses = [
            _c("acr", "ACR", "331"),
            _c("full", "Arrêt cardio-circulatoire", "331"),
        ]
        with patch(
            "backend.core.ai_qcm.service.item_title",
            return_value="Arrêt cardio-circulatoire",
        ):
            cid, title, item = _find_course("331", "", courses)
        assert cid == "full"

    def test_multi_match_item_fallback_longer_title(self):
        """Sans titre EDN, le plus long titre gagne."""
        courses = [
            _c("a", "ACR", "999"),
            _c("b", "Arrêt cardio-circulatoire", "999"),
        ]
        with patch("backend.core.ai_qcm.service.item_title", return_value=""):
            cid, title, item = _find_course("999", "", courses)
        assert cid == "b"

    def test_title_match_fallback(self):
        """Sans item_number, fallback sur titre exact."""
        courses = [_c("a", "Dyslipidémies", "")]
        cid, title, item = _find_course("", "Dyslipidémies", courses)
        assert cid == "a"
