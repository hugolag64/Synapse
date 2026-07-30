"""Tests for the grouped Annales list page's filtering logic."""

from __future__ import annotations

import pytest

from backend.core.reviews import local_store


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def _seed_annale(source_url: str, matiere: str, faculte: str, annee: int, type_annale: str) -> int:
    return local_store.create_uness_annale(
        source_url=source_url,
        collected_at="2026-07-30T18:21:37+00:00",
        faculte=faculte,
        niveau="DFASM1",
        annee=annee,
        matiere=matiere,
        titre=f"Titre {matiere}",
        type_annale=type_annale,
    )


def test_annales_list_filters_by_matiere_faculte_annee_and_type() -> None:
    _seed_annale("url-1", "GÉRIATRIE", "Faculté de La Réunion", 2024, "matiere")
    _seed_annale("url-2", "NEUROLOGIE", "Faculté de Paris Saclay", 2025, "concours_blanc")

    from frontend.pages.annales import _filtered_annales

    assert len(_filtered_annales(matiere="GÉRIATRIE")) == 1
    assert len(_filtered_annales(faculte="Faculté de Paris Saclay")) == 1
    assert len(_filtered_annales(annee=2024)) == 1
    assert len(_filtered_annales(type_annale="concours_blanc")) == 1
    assert len(_filtered_annales()) == 2
