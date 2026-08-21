from unittest.mock import Mock, patch


def test_upload_audio_file_does_resumable_upload_and_returns_uri(tmp_path):
    from backend.core.ai import batch_client

    audio = tmp_path / "correction.mp3"
    audio.write_bytes(b"fake-audio-bytes")

    start_response = Mock(headers={"X-Goog-Upload-URL": "https://upload.example/session-1"})
    start_response.raise_for_status = Mock()
    finalize_response = Mock()
    finalize_response.raise_for_status = Mock()
    finalize_response.json.return_value = {
        "file": {"uri": "files/abc123", "name": "files/abc123", "mimeType": "audio/mpeg"}
    }

    with patch("backend.core.ai.batch_client.requests.post", side_effect=[start_response, finalize_response]) as mock_post:
        result = batch_client.upload_audio_file(audio, api_key="fake-key", timeout=30)

    assert result.uri == "files/abc123"
    assert result.mime_type == "audio/mpeg"
    start_call, finalize_call = mock_post.call_args_list
    assert start_call.kwargs["headers"]["X-Goog-Upload-Command"] == "start"
    assert finalize_call.args[0] == "https://upload.example/session-1"


def test_create_batch_job_posts_batch_generate_content():
    from backend.core.ai import batch_client

    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = {"name": "batches/job-1"}

    with patch("backend.core.ai.batch_client.requests.post", return_value=response) as mock_post:
        handle = batch_client.create_batch_job(
            "gemini-flash", {"batch": {"display_name": "conf-1"}}, api_key="fake-key", timeout=30,
        )

    assert handle.name == "batches/job-1"
    assert "gemini-flash:batchGenerateContent" in mock_post.call_args.args[0]


def test_get_batch_job_parses_succeeded_state_with_inlined_responses():
    from backend.core.ai import batch_client

    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = {
        "name": "batches/job-1",
        "done": True,
        "metadata": {"state": "JOB_STATE_SUCCEEDED"},
        "response": {"inlinedResponses": [{"response": {"text": "ok"}}]},
    }

    with patch("backend.core.ai.batch_client.requests.get", return_value=response):
        status = batch_client.get_batch_job("batches/job-1", api_key="fake-key", timeout=30)

    assert status.done is True
    assert status.state == "JOB_STATE_SUCCEEDED"
    assert status.inlined_responses == [{"response": {"text": "ok"}}]
    assert status.responses_file_name is None


def test_get_batch_job_parses_failed_state():
    from backend.core.ai import batch_client

    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = {
        "name": "batches/job-1", "done": True,
        "metadata": {"state": "JOB_STATE_FAILED"},
        "error": {"message": "quota exceeded"},
    }

    with patch("backend.core.ai.batch_client.requests.get", return_value=response):
        status = batch_client.get_batch_job("batches/job-1", api_key="fake-key", timeout=30)

    assert status.state == "JOB_STATE_FAILED"
    assert status.error == "quota exceeded"


def test_download_batch_results_returns_bytes():
    from backend.core.ai import batch_client

    response = Mock()
    response.raise_for_status = Mock()
    response.content = b'{"key": "q1", "response": {}}\n'

    with patch("backend.core.ai.batch_client.requests.get", return_value=response) as mock_get:
        content = batch_client.download_batch_results("files/results-1", api_key="fake-key", timeout=30)

    assert content == b'{"key": "q1", "response": {}}\n'
    assert "files/results-1:download" in mock_get.call_args.args[0]
