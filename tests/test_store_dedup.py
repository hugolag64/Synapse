"""Tests pour DataStore._deduplicate_cours()"""
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from backend.state.store import DataStore
from backend.core.notion.models import Cours


def _make_cours(id_: str, title: str, item_number: str = "", college: list = None) -> Cours:
    return Cours(
        id=id_,
        title=title,
        item_number=item_number,
        college=college or [],
        created_time=datetime(2024, 1, 1),
    )


class TestDeduplicateCours:
    def test_no_duplicates_unchanged(self):
        cours = [
            _make_cours("a", "Arrêt cardio-circulatoire", "331"),
            _make_cours("b", "Dyslipidémies", "223"),
        ]
        result = DataStore._deduplicate_cours(cours)
        assert len(result) == 2

    def test_no_item_number_kept(self):
        cours = [
            _make_cours("a", "Cours sans item", ""),
            _make_cours("b", "Autre sans item", ""),
        ]
        result = DataStore._deduplicate_cours(cours)
        assert len(result) == 2

    def test_duplicate_keeps_canonical(self):
        """Doit conserver le cours dont le titre matche mieux le titre EDN."""
        cours = [
            _make_cours("acr", "ACR", "331"),
            _make_cours("full", "Arrêt cardio-circulatoire", "331"),
        ]
        # items_mapping.item_title(331) → "Arrêt cardio-circulatoire"
        with patch(
            "backend.state.store.item_title",
            return_value="Arrêt cardio-circulatoire",
        ):
            result = DataStore._deduplicate_cours(cours)
        assert len(result) == 1
        assert result[0].id == "full"

    def test_duplicate_with_empty_canonical_keeps_longer_title(self):
        """Si pas de titre EDN, garde le titre le plus long."""
        cours = [
            _make_cours("a", "ACR", "999"),
            _make_cours("b", "Arrêt cardio-circulatoire", "999"),
        ]
        with patch("backend.state.store.item_title", return_value=""):
            result = DataStore._deduplicate_cours(cours)
        assert len(result) == 1
        assert result[0].id == "b"

    def test_three_duplicates_keeps_best(self):
        cours = [
            _make_cours("a", "ACR", "331"),
            _make_cours("b", "Arrêt cardiaque", "331"),
            _make_cours("c", "Arrêt cardio-circulatoire", "331"),
        ]
        with patch(
            "backend.state.store.item_title",
            return_value="Arrêt cardio-circulatoire",
        ):
            result = DataStore._deduplicate_cours(cours)
        assert len(result) == 1
        assert result[0].id == "c"

    def test_mixed_items_and_no_item(self):
        cours = [
            _make_cours("a", "ACR", "331"),
            _make_cours("b", "Arrêt cardio-circulatoire", "331"),
            _make_cours("c", "Sans item", ""),
            _make_cours("d", "Dyslipidémies", "223"),
        ]
        with patch(
            "backend.state.store.item_title",
            side_effect=lambda n: "Arrêt cardio-circulatoire" if n == "331" else "",
        ):
            result = DataStore._deduplicate_cours(cours)
        assert len(result) == 3  # best 331 + sans item + 223
        ids = {c.id for c in result}
        assert "a" not in ids  # ACR éliminé
        assert "b" in ids
        assert "c" in ids
        assert "d" in ids
