from uuid import uuid4

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


def test_annale_provenance_accepts_ednpro_source():
    annale_id = local_store.create_uness_annale(
        source_url=f"https://ednpro.app/annales/2023-p1-provenance-test-{uuid4().hex}",
        collected_at="2026-08-04T08:00:00+00:00",
        faculte="EDNpro",
        niveau="EDN",
        annee=2023,
        matiere="Cardiologie",
        titre="EDN 2023 — P1",
        type_annale="edn_complet",
        source="EDNpro",
        source_exam_id="2023-p1",
    )

    row = local_store.get_uness_annale(annale_id)

    assert row["source"] == "EDNpro"
    assert row["source_exam_id"] == "2023-p1"
