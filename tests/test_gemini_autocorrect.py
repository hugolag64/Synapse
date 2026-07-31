"""Tests for the Gemini API auto-correct orchestrator (backend/core/uness/gemini_autocorrect.py)."""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from backend.core.ai.routing import AIModel, AIResponse, AIServiceError
from backend.core.uness import gemini_autocorrect, import_service


@pytest.fixture(autouse=True)
def _isolated_verified_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(import_service, "VERIFIED_DIR", tmp_path / "verifies")
    return tmp_path / "verifies"


def _bridge_file(folder, *, title="DP1\nTest", images=None):
    payload = {
        "bridge_schema_version": 1,
        "source": {
            "source_url": "https://entrainement.uness.fr/annales/course/view.php?id=1",
            "collected_at": "2026-07-30T09:00:00+00:00",
            "collection_status": "submitted",
        },
        "instructions": "...",
        "prompt": "Corrige ce quiz.",
        "contents": [
            {
                "title": title,
                "url": "https://entrainement.uness.fr/x",
                "html": "<div>question html</div>",
                "status": "reviewed",
                "images": images or [],
            }
        ],
    }
    path = folder / "dp1-20260730T090000Z.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _quiz_response(title="DP1\nTest") -> AIResponse:
    payload = {"quiz_title": title, "questions": []}
    return AIResponse(text=json.dumps(payload), model=AIModel.FLASH, input_tokens=100, output_tokens=20)


def test_correct_directory_writes_raw_response_and_sums_tokens(tmp_path, _isolated_verified_dir):
    _bridge_file(tmp_path)
    service = Mock()
    service.generate.return_value = _quiz_response()

    result = gemini_autocorrect.correct_directory(tmp_path, service=service)

    assert result["errors"] == []
    assert len(result["corrected"]) == 1
    assert result["input_tokens"] == 100
    assert result["output_tokens"] == 20
    written = list(_isolated_verified_dir.glob("*.json"))
    assert len(written) == 1
    assert json.loads(written[0].read_text(encoding="utf-8")) == {"quiz_title": "DP1\nTest", "questions": []}


def test_correct_directory_processes_every_quiz_in_every_bridge(tmp_path, _isolated_verified_dir):
    _bridge_file(tmp_path, title="DP1\nTest")
    second = tmp_path / "kfp-20260730T090000Z.json"
    second.write_text(
        json.dumps(
            {
                "contents": [
                    {"title": "KFP\nTest", "html": "<div>kfp</div>", "images": []}
                ]
            }
        ),
        encoding="utf-8",
    )
    service = Mock()
    service.generate.side_effect = [_quiz_response("DP1\nTest"), _quiz_response("KFP\nTest")]

    result = gemini_autocorrect.correct_directory(tmp_path, service=service)

    assert len(result["corrected"]) == 2
    assert service.generate.call_count == 2


def test_correct_directory_sends_images_found_by_basename(tmp_path, _isolated_verified_dir):
    (tmp_path / "dermato1.jpg").write_bytes(b"fake-jpeg-bytes")
    _bridge_file(
        tmp_path,
        images=[{"question_id": "q1", "filename": "uness-stamp/images/dermato1.jpg"}],
    )
    service = Mock()
    service.generate.return_value = _quiz_response()

    gemini_autocorrect.correct_directory(tmp_path, service=service)

    _, kwargs = service.generate.call_args
    sent_images = kwargs["images"]
    assert len(sent_images) == 1
    assert sent_images[0].mime_type == "image/jpeg"
    assert sent_images[0].data == b"fake-jpeg-bytes"


def test_correct_directory_reports_missing_image_but_still_writes_correction(tmp_path, _isolated_verified_dir):
    _bridge_file(
        tmp_path,
        images=[{"question_id": "q1", "filename": "uness-stamp/images/missing.jpg"}],
    )
    service = Mock()
    service.generate.return_value = _quiz_response()

    result = gemini_autocorrect.correct_directory(tmp_path, service=service)

    assert len(result["corrected"]) == 1
    assert any("missing.jpg" in error["error"] for error in result["errors"])


def test_correct_directory_records_error_for_invalid_json_response_without_aborting_others(
    tmp_path, _isolated_verified_dir
):
    _bridge_file(tmp_path, title="DP1\nTest")
    second = tmp_path / "kfp-20260730T090000Z.json"
    second.write_text(
        json.dumps({"contents": [{"title": "KFP\nTest", "html": "<div>kfp</div>", "images": []}]}),
        encoding="utf-8",
    )
    service = Mock()
    service.generate.side_effect = [
        AIResponse(text="not valid json", model=AIModel.FLASH, input_tokens=10, output_tokens=1),
        _quiz_response("KFP\nTest"),
    ]

    result = gemini_autocorrect.correct_directory(tmp_path, service=service)

    assert len(result["corrected"]) == 1
    assert len(result["errors"]) == 1


def test_correct_directory_reports_missing_folder(tmp_path, _isolated_verified_dir):
    result = gemini_autocorrect.correct_directory(tmp_path / "does-not-exist", service=Mock())

    assert result["corrected"] == []
    assert len(result["errors"]) == 1


def test_correct_directory_continues_after_gemini_api_error_on_one_quiz(tmp_path, _isolated_verified_dir):
    _bridge_file(tmp_path, title="DP1\nTest")
    second = tmp_path / "kfp-20260730T090000Z.json"
    second.write_text(
        json.dumps({"contents": [{"title": "KFP\nTest", "html": "<div>kfp</div>", "images": []}]}),
        encoding="utf-8",
    )
    service = Mock()
    service.generate.side_effect = [
        AIServiceError("Gemini inaccessible : timeout"),
        _quiz_response("KFP\nTest"),
    ]

    result = gemini_autocorrect.correct_directory(tmp_path, service=service)

    assert len(result["corrected"]) == 1
    assert len(result["errors"]) == 1
    assert "Gemini inaccessible" in result["errors"][0]["error"]
