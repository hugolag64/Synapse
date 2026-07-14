"""Tests unitaires — _compute_stats enrichi (frontend/pages/colleges.py).

Vérifie que _compute_stats agrège correctement le statut académique du
collège (knowledge.store) et l'avancement du triage (knowledge.service),
en plus des stats de couverture déjà existantes.
"""
from dataclasses import dataclass

import pytest


# ── Fixture : DB temporaire isolée (même pattern que tests/test_knowledge_store.py) ──

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import backend.core.reviews.local_store as ls
    import backend.core.knowledge.store as ks

    test_db = tmp_path / "test.db"
    monkeypatch.setattr(ls, "DB_PATH", test_db)
    monkeypatch.setattr(ls, "_DB", None)
    ls.init_db()
    ks.init_knowledge_tables()
    yield
    if ls._DB is not None:
        ls._DB.close()
    monkeypatch.setattr(ls, "_DB", None)


@dataclass
class _FakeCours:
    id: str
    date_1ere_lecture: str | None


_FAKE_COURSES = [
    _FakeCours(id="course-1", date_1ere_lecture="2026-01-01"),
    _FakeCours(id="course-2", date_1ere_lecture=None),
    _FakeCours(id="course-3", date_1ere_lecture="2026-02-01"),
]


@pytest.fixture(autouse=True)
def fake_courses(monkeypatch):
    from backend.state.store import data_store

    monkeypatch.setattr(
        data_store, "get_cours_for_college", lambda name: list(_FAKE_COURSES)
    )


def _import_compute_stats():
    from frontend.pages.colleges import _compute_stats
    return _compute_stats


def test_college_non_declare_est_non_etudie_sans_items_situes():
    _compute_stats = _import_compute_stats()
    stats = _compute_stats("Cardiovasculaire")

    assert stats["status"] == "non_etudie"
    assert stats["situes"] == 0
    assert stats["n_items"] == 3


def test_college_valide_reflete_son_statut_et_le_nombre_total_d_items():
    import backend.core.knowledge.store as ks

    ks.set_college_status("Cardiovasculaire", "valide")

    _compute_stats = _import_compute_stats()
    stats = _compute_stats("Cardiovasculaire")

    assert stats["status"] == "valide"
    assert stats["n_items"] == 3
    assert stats["situes"] == 0


def test_situes_compte_les_items_declares_parmi_les_cours_du_college():
    import backend.core.knowledge.store as ks

    ks.set_college_status("Cardiovasculaire", "valide")
    ks.set_item_state("course-1", "solide")
    ks.set_item_state("course-3", "correct")

    _compute_stats = _import_compute_stats()
    stats = _compute_stats("Cardiovasculaire")

    assert stats["situes"] == 2
    assert stats["n_items"] == 3
    assert stats["status"] == "valide"


def test_stats_de_couverture_existantes_restent_correctes():
    _compute_stats = _import_compute_stats()
    stats = _compute_stats("Cardiovasculaire")

    assert stats["total"] == 3
    assert stats["started"] == 2
    assert stats["pct"] == pytest.approx(2 / 3)
