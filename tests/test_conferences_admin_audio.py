from unittest.mock import Mock, patch


def test_handle_audio_upload_calls_save_conference_audio(monkeypatch):
    from frontend.components import conferences_admin

    fake_event = Mock()
    fake_event.name = "correction.mp3"
    fake_event.content.read.return_value = b"fake-audio"

    with patch(
        "frontend.components.conferences_admin.audio_service.save_conference_audio"
    ) as mock_save:
        conferences_admin._handle_audio_upload(conference_id=5, event=fake_event)

    mock_save.assert_called_once_with(5, filename="correction.mp3", content=b"fake-audio")
