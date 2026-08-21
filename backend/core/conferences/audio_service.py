"""Upload et validation de l'enregistrement audio d'une conférence."""
from __future__ import annotations

import hashlib
from pathlib import Path

from backend.core.reviews import local_store

AUDIO_DIR = Path("data/conferences/audio")
MAX_AUDIO_BYTES = 300 * 1024 * 1024  # 300 Mo
_ALLOWED_EXTENSIONS = {".mp3", ".m4a", ".wav"}


def hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def save_conference_audio(conference_id: int, *, filename: str, content: bytes) -> dict:
    """Valide, sauvegarde sur disque et enregistre l'audio d'une conférence.

    Lève ValueError (rien n'est écrit) si le format est inconnu, le fichier
    vide ou trop volumineux.
    """
    if local_store.get_conference(conference_id) is None:
        raise ValueError(f"Conférence introuvable: {conference_id}")

    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise ValueError(f"Format audio non supporté: {suffix or '(aucun)'}")
    if not content:
        raise ValueError("Le fichier audio est vide")
    if len(content) > MAX_AUDIO_BYTES:
        raise ValueError(f"Fichier audio trop volumineux (> {MAX_AUDIO_BYTES // (1024 * 1024)} Mo)")

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    target = AUDIO_DIR / f"{conference_id}{suffix}"
    target.write_bytes(content)

    audio_hash = hash_bytes(content)
    return local_store.set_conference_audio(
        conference_id, audio_path=str(target), audio_hash=audio_hash,
    )
