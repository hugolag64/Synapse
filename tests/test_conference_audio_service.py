import datetime

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    from backend.core.reviews import local_store
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "audio-service.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield local_store
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


@pytest.fixture
def conference(isolated_db):
    _, conf = isolated_db.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="Cardiologie", match_status="matched",
        college_name="Cardiologie", source_file="planning.xlsx",
    )
    return conf


def test_save_conference_audio_writes_file_and_hash(tmp_path, monkeypatch, conference):
    from backend.core.conferences import audio_service
    monkeypatch.setattr(audio_service, "AUDIO_DIR", tmp_path / "audio")

    result = audio_service.save_conference_audio(
        conference["id"], filename="correction.mp3", content=b"fake-mp3-bytes",
    )

    assert result["audio_path"].endswith(".mp3")
    saved = tmp_path / "audio" / f"{conference['id']}.mp3"
    assert saved.read_bytes() == b"fake-mp3-bytes"
    assert result["audio_hash"] == audio_service.hash_bytes(b"fake-mp3-bytes")


def test_save_conference_audio_rejects_unsupported_format(tmp_path, monkeypatch, conference):
    from backend.core.conferences import audio_service
    monkeypatch.setattr(audio_service, "AUDIO_DIR", tmp_path / "audio")

    with pytest.raises(ValueError, match="upport"):
        audio_service.save_conference_audio(
            conference["id"], filename="correction.pdf", content=b"not-audio",
        )


def test_save_conference_audio_rejects_empty_file(tmp_path, monkeypatch, conference):
    from backend.core.conferences import audio_service
    monkeypatch.setattr(audio_service, "AUDIO_DIR", tmp_path / "audio")

    with pytest.raises(ValueError, match="vide"):
        audio_service.save_conference_audio(conference["id"], filename="correction.mp3", content=b"")


def test_save_conference_audio_rejects_too_large_file(tmp_path, monkeypatch, conference):
    from backend.core.conferences import audio_service
    monkeypatch.setattr(audio_service, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(audio_service, "MAX_AUDIO_BYTES", 10)

    with pytest.raises(ValueError, match="volumineux"):
        audio_service.save_conference_audio(
            conference["id"], filename="correction.mp3", content=b"0123456789ABCDEF",
        )
