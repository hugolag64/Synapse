"""Tests for the Gemini API auto-correct orchestrator (backend/core/uness/gemini_autocorrect.py)."""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from backend.core.ai.routing import AIModel, AIResponse, AIServiceError, AITask
from backend.core.reviews import local_store
from backend.core.uness import gemini_autocorrect, gemini_conversion, import_service


@pytest.fixture(autouse=True)
def _isolated_verified_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(import_service, "VERIFIED_DIR", tmp_path / "verifies")
    return tmp_path / "verifies"


@pytest.fixture(autouse=True)
def _isolated_local_store_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "local-store-test.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def _bridge_file(folder, *, title="DP1\nTest", images=None, name="dp1-20260730T090000Z.json"):
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
    path = folder / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _quiz_response(title="DP1\nTest") -> AIResponse:
    payload = {"quiz_title": title, "questions": []}
    return AIResponse(text=json.dumps(payload), model=AIModel.FLASH, input_tokens=100, output_tokens=20)


def test_correct_directory_writes_already_canonical_exam_and_sums_tokens(tmp_path, _isolated_verified_dir):
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
    written_payload = json.loads(written[0].read_text(encoding="utf-8"))
    # Already-canonical (UnessExam.to_dict()), not the raw {"quiz_title", "questions"}
    # AI response shape — so the downstream scan never needs to re-match a bridge by
    # title (see test_correct_directory_output_never_needs_bridge_title_lookup below).
    assert gemini_conversion.is_raw_ai_response(written_payload) is False
    assert written_payload["provenance"]["source_url"] == (
        "https://entrainement.uness.fr/annales/course/view.php?id=1"
    )
    assert written_payload["questions"] == []


def test_correct_directory_tolerates_trailing_extra_data_after_valid_json(tmp_path, _isolated_verified_dir):
    # Seen live: Gemini sometimes appends extra content after a fully valid JSON
    # response, which json.loads rejects outright ("Extra data: line N column 1").
    # A response is still usable as long as the JSON value itself parses cleanly.
    _bridge_file(tmp_path)
    service = Mock()
    payload = json.dumps({"quiz_title": "DP1\nTest", "questions": []})
    service.generate.return_value = AIResponse(
        text=payload + "\n\nNote: correction terminée.",
        model=AIModel.FLASH,
        input_tokens=100,
        output_tokens=20,
    )

    result = gemini_autocorrect.correct_directory(tmp_path, service=service)

    assert result["errors"] == []
    assert len(result["corrected"]) == 1


def test_correct_directory_output_never_needs_bridge_title_lookup(tmp_path, _isolated_verified_dir):
    # Two à_vérifier session folders sharing the exact same quiz title (e.g. the
    # same course collected twice) used to make the downstream scan's title-based
    # bridge search ambiguous and fail — even though correct_directory already knew
    # exactly which bridge it used. Writing an already-canonical exam sidesteps that
    # search entirely for API-corrected files.
    folder_a = tmp_path / "session-a"
    folder_a.mkdir()
    folder_b = tmp_path / "session-b"
    folder_b.mkdir()
    _bridge_file(folder_a, title="mDP1\nTest")
    _bridge_file(folder_b, title="mDP1\nTest")
    service = Mock()
    service.generate.return_value = _quiz_response("mDP1\nTest")

    result = gemini_autocorrect.correct_directory(folder_a, service=service)

    assert len(result["corrected"]) == 1
    written = list(_isolated_verified_dir.glob("*.json"))
    written_payload = json.loads(written[0].read_text(encoding="utf-8"))
    assert gemini_conversion.is_raw_ai_response(written_payload) is False


def test_correct_directory_processes_every_quiz_in_every_bridge(tmp_path, _isolated_verified_dir):
    _bridge_file(tmp_path, title="DP1\nTest")
    _bridge_file(tmp_path, title="KFP\nTest", name="kfp-20260730T090000Z.json")
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


def test_correct_directory_uses_lite_model_without_images_and_flash_with_images(tmp_path, _isolated_verified_dir):
    (tmp_path / "dermato1.jpg").write_bytes(b"fake-jpeg-bytes")
    _bridge_file(
        tmp_path,
        title="DP1\nTest",
        images=[{"question_id": "q1", "filename": "uness-stamp/images/dermato1.jpg"}],
        name="dp1-20260730T090000Z.json",
    )
    _bridge_file(tmp_path, title="KFP\nTest", name="kfp-20260730T090000Z.json")
    service = Mock()
    service.generate.side_effect = [_quiz_response("DP1\nTest"), _quiz_response("KFP\nTest")]

    gemini_autocorrect.correct_directory(tmp_path, service=service)

    tasks_used = [call.args[0] for call in service.generate.call_args_list]
    assert AITask.UNESS_CORRECTION_VISUAL in tasks_used
    assert AITask.UNESS_CORRECTION in tasks_used


def test_correct_directory_does_not_publish_visual_correction_without_human_validation(
    tmp_path, _isolated_verified_dir
):
    (tmp_path / "dermato1.jpg").write_bytes(b"fake-jpeg-bytes")
    _bridge_file(
        tmp_path,
        images=[{"question_id": "q1", "filename": "uness-stamp/images/dermato1.jpg"}],
    )
    service = Mock()
    service.generate.return_value = _quiz_response()

    result = gemini_autocorrect.correct_directory(tmp_path, service=service)

    assert result["corrected"] == []
    assert any("validation humaine" in error["error"] for error in result["errors"])


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
    _bridge_file(tmp_path, title="KFP\nTest", name="kfp-20260730T090000Z.json")
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
    _bridge_file(tmp_path, title="KFP\nTest", name="kfp-20260730T090000Z.json")
    service = Mock()
    service.generate.side_effect = [
        AIServiceError("Gemini inaccessible : timeout"),
        _quiz_response("KFP\nTest"),
    ]

    result = gemini_autocorrect.correct_directory(tmp_path, service=service)

    assert len(result["corrected"]) == 1
    assert len(result["errors"]) == 1
    assert "Gemini inaccessible" in result["errors"][0]["error"]


def test_correct_directory_rejects_a_quiz_with_fewer_questions_than_the_source_html(
    tmp_path, _isolated_verified_dir
):
    """Le cas exact constaté en prod : DP1 a 6 questions sur UNESS (6 div.que
    dans le HTML du bridge), Gemini n'en renvoie que 5 dans un JSON par
    ailleurs valide — ça doit être traité comme un échec, rien n'est écrit."""
    html = "".join(f'<div class="que"><div class="qtext">Q{i}</div></div>' for i in range(1, 7))
    _bridge_file(tmp_path, name="dp1-20260730T090000Z.json")
    bridge_path = tmp_path / "dp1-20260730T090000Z.json"
    payload = json.loads(bridge_path.read_text(encoding="utf-8"))
    payload["contents"][0]["html"] = html
    bridge_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    service = Mock()
    five_questions = {
        "quiz_title": "DP1\nTest",
        "questions": [
            {
                "id": f"q{i}",
                "type_question": "QRM",
                "enonce": f"Q{i}",
                "propositions": [
                    {
                        "id": "A",
                        "texte": "Proposition A",
                        "reponse_officielle": True,
                        "verdict_ia": True,
                        "explication": "Car A.",
                        "confiance_ia": 0.9,
                    }
                ],
            }
            for i in range(1, 6)
        ],
    }
    service.generate.return_value = AIResponse(
        text=json.dumps(five_questions), model=AIModel.FLASH, input_tokens=100, output_tokens=20
    )

    result = gemini_autocorrect.correct_directory(tmp_path, service=service)

    assert result["corrected"] == []
    assert len(result["errors"]) == 1
    assert "5/6" in result["errors"][0]["error"]
    assert list(_isolated_verified_dir.glob("*.json")) == []


def test_correct_directory_accepts_a_quiz_whose_question_count_matches_the_source_html(
    tmp_path, _isolated_verified_dir
):
    """Contrôle négatif : un compte qui correspond ne doit jamais être bloqué —
    couvre aussi le cas des fixtures existantes dont le HTML factice
    ("<div>question html</div>") ne contient aucun div.que (0 attendu, 0 reçu)."""
    html = "".join(f'<div class="que"><div class="qtext">Q{i}</div></div>' for i in range(1, 4))
    _bridge_file(tmp_path, name="dp1-20260730T090000Z.json")
    bridge_path = tmp_path / "dp1-20260730T090000Z.json"
    payload = json.loads(bridge_path.read_text(encoding="utf-8"))
    payload["contents"][0]["html"] = html
    bridge_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    service = Mock()
    three_questions = {
        "quiz_title": "DP1\nTest",
        "questions": [
            {
                "id": f"q{i}",
                "type_question": "QRM",
                "enonce": f"Q{i}",
                "propositions": [
                    {
                        "id": "A",
                        "texte": "Proposition A",
                        "reponse_officielle": True,
                        "verdict_ia": True,
                        "explication": "Car A.",
                        "confiance_ia": 0.9,
                    }
                ],
            }
            for i in range(1, 4)
        ],
    }
    service.generate.return_value = AIResponse(
        text=json.dumps(three_questions), model=AIModel.FLASH, input_tokens=100, output_tokens=20
    )

    result = gemini_autocorrect.correct_directory(tmp_path, service=service)

    assert len(result["corrected"]) == 1
    assert result["errors"] == []


def test_correct_directory_records_a_pending_failure_on_invalid_json(tmp_path, _isolated_verified_dir):
    _bridge_file(tmp_path, title="DP1\nTest")
    service = Mock()
    service.generate.return_value = AIResponse(
        text="not valid json", model=AIModel.FLASH, input_tokens=10, output_tokens=1
    )

    gemini_autocorrect.correct_directory(tmp_path, service=service)

    failures = local_store.list_pending_uness_correction_failures()
    assert len(failures) == 1
    assert failures[0]["quiz_title"] == "DP1\nTest"
    assert failures[0]["collected_at"] == "2026-07-30T09:00:00+00:00"


def test_correct_directory_resolves_a_previously_recorded_failure_on_success(tmp_path, _isolated_verified_dir):
    local_store.record_uness_correction_failure(
        bridge_folder=str(tmp_path),
        quiz_title="DP1\nTest",
        collected_at="2026-07-30T09:00:00+00:00",
        error_message="ancien échec",
    )
    _bridge_file(tmp_path, title="DP1\nTest")
    service = Mock()
    service.generate.return_value = _quiz_response("DP1\nTest")

    gemini_autocorrect.correct_directory(tmp_path, service=service)

    assert local_store.list_pending_uness_correction_failures() == []


def test_correct_directory_does_not_record_a_failure_when_correction_succeeds(tmp_path, _isolated_verified_dir):
    _bridge_file(tmp_path, title="DP1\nTest")
    service = Mock()
    service.generate.return_value = _quiz_response("DP1\nTest")

    gemini_autocorrect.correct_directory(tmp_path, service=service)

    assert local_store.list_pending_uness_correction_failures() == []


@pytest.fixture
def _isolated_review_dirs(tmp_path, monkeypatch):
    to_review = tmp_path / "a_verifier"
    archive = tmp_path / "archives"
    to_review.mkdir()
    archive.mkdir()
    monkeypatch.setattr(import_service, "TO_REVIEW_DIR", to_review)
    monkeypatch.setattr(import_service, "ARCHIVE_DIR", archive)
    return to_review, archive


def test_retry_failed_quiz_relocates_a_bridge_still_in_a_verifier(
    _isolated_review_dirs, _isolated_verified_dir
):
    to_review, _archive = _isolated_review_dirs
    _bridge_file(to_review, title="SQI1\nTest", name="sqi1-20260801T090000Z.json")
    failure_id = local_store.record_uness_correction_failure(
        bridge_folder=str(to_review),
        quiz_title="SQI1\nTest",
        collected_at="2026-07-30T09:00:00+00:00",
        error_message="ancien échec",
    )
    service = Mock()
    service.generate.return_value = _quiz_response("SQI1\nTest")

    result = gemini_autocorrect.retry_failed_quiz(failure_id, service=service)

    assert result == {"success": True, "error": None}
    assert local_store.list_pending_uness_correction_failures() == []
    assert len(list(_isolated_verified_dir.glob("*.json"))) == 1


def test_retry_failed_quiz_relocates_a_bridge_moved_to_archives(
    _isolated_review_dirs, _isolated_verified_dir
):
    """Une fois les quiz voisins réussis, import_service déplace le dossier de
    session entier (JSON + images) vers archives/<faculté>/ — le retry doit
    suivre le bridge jusque là."""
    _to_review, archive = _isolated_review_dirs
    archived_faculty_dir = archive / "pneumologie"
    archived_faculty_dir.mkdir()
    _bridge_file(archived_faculty_dir, title="SQI1\nTest", name="a_verifier-sqi1-20260801T090000Z.json")
    failure_id = local_store.record_uness_correction_failure(
        bridge_folder="UNESS/à_vérifier/session-old",  # chemin périmé, ne doit plus être utilisé pour chercher
        quiz_title="SQI1\nTest",
        collected_at="2026-07-30T09:00:00+00:00",
        error_message="ancien échec",
    )
    service = Mock()
    service.generate.return_value = _quiz_response("SQI1\nTest")

    result = gemini_autocorrect.retry_failed_quiz(failure_id, service=service)

    assert result == {"success": True, "error": None}


def test_retry_failed_quiz_reports_a_clear_error_when_bridge_is_gone(
    _isolated_review_dirs, _isolated_verified_dir
):
    failure_id = local_store.record_uness_correction_failure(
        bridge_folder="UNESS/à_vérifier/session-old",
        quiz_title="SQI1\nTest",
        collected_at="2026-07-30T09:00:00+00:00",
        error_message="ancien échec",
    )

    result = gemini_autocorrect.retry_failed_quiz(failure_id, service=Mock())

    assert result["success"] is False
    assert "introuvable" in result["error"].lower()
    failures = local_store.list_pending_uness_correction_failures()
    assert len(failures) == 1  # toujours pending, pas perdu


def test_retry_failed_quiz_reports_unknown_failure_id(_isolated_verified_dir):
    result = gemini_autocorrect.retry_failed_quiz(999, service=Mock())

    assert result == {"success": False, "error": "Entrée introuvable"}
