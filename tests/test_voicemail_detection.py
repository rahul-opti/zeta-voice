import tempfile
from unittest.mock import Mock, patch

import pytest

from carriage_services.voicemail_detection.voicemail_detection import VoicemailDetector


@pytest.fixture()
def mock_settings():
    with patch("carriage_services.voicemail_detection.voicemail_detection.settings") as mock:
        settings_instance = Mock()
        settings_instance.voicemail_detection.VOICEMAIL_DETECTION_MODEL = "gpt-4o-mini"
        mock.return_value = settings_instance
        yield mock


@pytest.fixture()
def mock_paths():
    with patch("carriage_services.voicemail_detection.voicemail_detection.paths") as mock_paths:
        with tempfile.NamedTemporaryFile(suffix=".j2", delete=False) as f:
            mock_paths.VOICEMAIL_DETECTION_PROMPT_PATH = f.name
        yield mock_paths


@pytest.fixture()
def sample_prompt_template():
    template_content = """
    Analyze the following transcription to determine if it's a voicemail system or answering machine.

    Transcription: {{ transcription }}

    Determine if this is a voicemail system or answering machine.
    """

    with tempfile.NamedTemporaryFile(mode="w", suffix=".j2", delete=False) as f:
        f.write(template_content)
        yield f.name


@patch("carriage_services.voicemail_detection.voicemail_detection.paths")
@patch("carriage_services.voicemail_detection.voicemail_detection.acompletion")
@pytest.mark.asyncio()
async def test_detect_voicemail(
    mock_acompletion: Mock,
    mock_paths: Mock,
    mock_settings: Mock,
    sample_prompt_template: str,
):
    """Test successful voicemail detection."""
    mock_paths.VOICEMAIL_DETECTION_PROMPT_PATH = sample_prompt_template

    mock_response = Mock()
    mock_response.choices = [Mock(message=Mock(content='{"is_voicemail": true}'))]
    mock_acompletion.return_value = mock_response

    detector = VoicemailDetector()
    result = await detector.detect_voicemail(
        transcription="Hello, you've reached the voicemail of John Doe. Please leave a message after the beep."
    )

    assert result is not None
    assert result.is_voicemail is True
    mock_acompletion.assert_called_once()


@patch("carriage_services.voicemail_detection.voicemail_detection.paths")
@patch("carriage_services.voicemail_detection.voicemail_detection.acompletion")
@pytest.mark.asyncio()
async def test_detect_voicemail_not_voicemail(
    mock_acompletion: Mock,
    mock_paths: Mock,
    mock_settings: Mock,
    sample_prompt_template: str,
):
    """Test voicemail detection when it's not a voicemail."""
    mock_paths.VOICEMAIL_DETECTION_PROMPT_PATH = sample_prompt_template

    mock_response = Mock()
    mock_response.choices = [Mock(message=Mock(content='{"is_voicemail": false}'))]
    mock_acompletion.return_value = mock_response

    detector = VoicemailDetector()
    result = await detector.detect_voicemail(transcription="Hello, this is John Doe speaking.")

    assert result is not None
    assert result.is_voicemail is False
    mock_acompletion.assert_called_once()
