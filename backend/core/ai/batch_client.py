"""Transport HTTP minimal vers la Gemini File API et Batch API (REST brut)."""
from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path

import requests

from backend.config.settings import settings
from backend.core.ai.gemini_client import GeminiClientError, _redact_provider_secrets

_UPLOAD_BASE = "https://generativelanguage.googleapis.com/upload/v1beta/files"
_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
_DOWNLOAD_BASE = "https://generativelanguage.googleapis.com/download/v1beta"


@dataclass(frozen=True)
class UploadedFile:
    uri: str
    name: str
    mime_type: str


@dataclass(frozen=True)
class BatchJobHandle:
    name: str


@dataclass(frozen=True)
class BatchJobStatus:
    name: str
    done: bool
    state: str
    inlined_responses: list | None
    responses_file_name: str | None
    error: str | None


def _resolve(api_key: str | None, timeout: float | None) -> tuple[str, float]:
    key = settings.gemini_api_key if api_key is None else api_key
    if not key:
        raise GeminiClientError("Aucune clé Gemini configurée")
    return key, (settings.gemini_timeout_seconds if timeout is None else timeout)


def upload_audio_file(path: Path, *, api_key: str | None = None, timeout: float | None = None) -> UploadedFile:
    """Upload resumable d'un fichier audio via la Gemini File API."""
    key, effective_timeout = _resolve(api_key, timeout)
    content = path.read_bytes()
    mime_type = mimetypes.guess_type(path.name)[0] or "audio/mpeg"

    try:
        start = requests.post(
            _UPLOAD_BASE,
            headers={
                "x-goog-api-key": key,
                "X-Goog-Upload-Protocol": "resumable",
                "X-Goog-Upload-Command": "start",
                "X-Goog-Upload-Header-Content-Length": str(len(content)),
                "X-Goog-Upload-Header-Content-Type": mime_type,
                "Content-Type": "application/json",
            },
            json={"file": {"display_name": path.name}},
            timeout=effective_timeout,
        )
        start.raise_for_status()
        upload_url = start.headers.get("X-Goog-Upload-URL") or start.headers.get("x-goog-upload-url")
        if not upload_url:
            raise GeminiClientError("Gemini n'a pas renvoyé d'URL d'upload")

        finalize = requests.post(
            upload_url,
            headers={
                "x-goog-api-key": key,
                "Content-Length": str(len(content)),
                "X-Goog-Upload-Offset": "0",
                "X-Goog-Upload-Command": "upload, finalize",
            },
            data=content,
            timeout=effective_timeout,
        )
        finalize.raise_for_status()
        payload = finalize.json()["file"]
    except GeminiClientError:
        raise
    except Exception as exc:
        raise GeminiClientError(f"Upload audio Gemini échoué : {_redact_provider_secrets(str(exc))}") from exc

    return UploadedFile(uri=payload["uri"], name=payload["name"], mime_type=payload.get("mimeType", mime_type))


def create_batch_job(
    model_id: str, request_body: dict, *, api_key: str | None = None, timeout: float | None = None,
) -> BatchJobHandle:
    key, effective_timeout = _resolve(api_key, timeout)
    url = f"{_API_BASE}/models/{model_id}:batchGenerateContent"
    try:
        response = requests.post(
            url, headers={"x-goog-api-key": key}, json=request_body, timeout=effective_timeout,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        raise GeminiClientError(f"Création du job Batch échouée : {_redact_provider_secrets(str(exc))}") from exc
    return BatchJobHandle(name=data["name"])


def get_batch_job(job_name: str, *, api_key: str | None = None, timeout: float | None = None) -> BatchJobStatus:
    key, effective_timeout = _resolve(api_key, timeout)
    url = f"{_API_BASE}/{job_name}"
    try:
        response = requests.get(url, headers={"x-goog-api-key": key}, timeout=effective_timeout)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        raise GeminiClientError(f"Consultation du job Batch échouée : {_redact_provider_secrets(str(exc))}") from exc

    metadata = data.get("metadata") or {}
    response_payload = data.get("response") or {}
    error_payload = data.get("error") or {}
    return BatchJobStatus(
        name=data.get("name", job_name),
        done=bool(data.get("done", False)),
        state=str(metadata.get("state", "")),
        inlined_responses=response_payload.get("inlinedResponses"),
        responses_file_name=response_payload.get("responsesFile"),
        error=error_payload.get("message"),
    )


def download_batch_results(
    responses_file_name: str, *, api_key: str | None = None, timeout: float | None = None,
) -> bytes:
    key, effective_timeout = _resolve(api_key, timeout)
    url = f"{_DOWNLOAD_BASE}/{responses_file_name}:download?alt=media"
    try:
        response = requests.get(url, headers={"x-goog-api-key": key}, timeout=effective_timeout)
        response.raise_for_status()
    except Exception as exc:
        raise GeminiClientError(f"Téléchargement des résultats Batch échoué : {_redact_provider_secrets(str(exc))}") from exc
    return response.content
