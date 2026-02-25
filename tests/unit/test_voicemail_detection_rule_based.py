"""Unit tests for rule-based VoicemailDetector using actual CSV file from repository."""

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from carriage_services.voicemail_detection.voicemail_detection import (
    VoicemailDetectionResult,
    VoicemailDetector,
)


@pytest.fixture()
def mock_settings_rule_based() -> Generator[MagicMock, None, None]:
    """Mock settings to use rule-based detector."""
    with patch("carriage_services.voicemail_detection.voicemail_detection.settings") as mock:
        mock.voicemail_detection.VOICEMAIL_DETECTOR_TYPE = "rule_based"
        yield mock


@pytest.fixture()
def rule_based_detector(mock_settings_rule_based: Any) -> VoicemailDetector:
    """Create a rule-based VoicemailDetector instance."""
    return VoicemailDetector()


class TestRuleBasedVoicemailDetector:
    """Test suite for rule-based voicemail detection."""

    # Test single-word patterns from CSV

    @staticmethod
    def test_detect_voicemail_single_word_voicemail(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with 'voicemail' pattern (single word from 'you have reached the voicemail')."""
        transcription = "You have reached the voicemail of John Smith"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_detect_voicemail_single_word_beep(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with 'beep' pattern (from 'after the beep')."""
        transcription = "Please leave a message after the beep"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_detect_voicemail_single_word_tone(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with 'tone' pattern (from 'at the tone')."""
        transcription = "Record your message at the tone"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    # Test multi-word phrase patterns from CSV

    @staticmethod
    def test_detect_voicemail_phrase_you_have_reached(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with 'you have reached' phrase."""
        transcription = "Hi, you have reached the office of Dr. Johnson"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_detect_voicemail_phrase_leave_a_message(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with 'leave a message' phrase."""
        transcription = "I'm not here right now, please leave a message"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_detect_voicemail_phrase_after_the_beep(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with 'after the beep' phrase."""
        transcription = "Please leave your name and number after the beep"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_detect_voicemail_phrase_leave_your_name(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with 'leave your name' phrase."""
        transcription = "Please leave your name and a brief message"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_detect_voicemail_phrase_leave_your_number(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with 'leave your number' phrase."""
        transcription = "Please leave your number and we will call you back"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_detect_voicemail_phrase_not_available(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with 'we are not available' phrase."""
        transcription = "We are not available to take your call right now"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_detect_voicemail_phrase_mailbox_is_full(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with 'mailbox is full' phrase."""
        transcription = "The mailbox is full and cannot accept messages"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_detect_voicemail_phrase_press_pound(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with 'press pound when finished' phrase."""
        transcription = "Leave your message and press pound when finished"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_detect_voicemail_phrase_thank_you_for_calling(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with 'thank you for calling' phrase."""
        transcription = "Thank you for calling our business, please leave a message"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_detect_voicemail_phrase_get_back_to_you(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with 'we will get back to you' phrase."""
        transcription = "Leave a message and we will get back to you soon"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_detect_voicemail_phrase_unable_to_take_call(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with 'unable to take your call' phrase."""
        transcription = "We are unable to take your call at this time"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_detect_voicemail_phrase_detailed_message(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with 'leave a detailed message' phrase."""
        transcription = "Please leave a detailed message with your information"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_detect_voicemail_phrase_record_your_message(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with 'record your message' phrase."""
        transcription = "Please record your message after the tone"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_detect_voicemail_phrase_reached_voicemail(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with 'you have reached the voicemail' phrase."""
        transcription = "You have reached the voicemail box of Sarah Williams"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_detect_voicemail_phrase_missed_your_call(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with 'sorry we missed your call' phrase."""
        transcription = "Sorry we missed your call, please leave a message"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_detect_voicemail_phrase_try_again_later(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with 'please try again later' phrase."""
        transcription = "We are closed now, please try again later or leave a message"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_detect_voicemail_phrase_call_important(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with 'your call is important to us' phrase."""
        transcription = "Your call is important to us, please hold or leave a message"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_detect_voicemail_phrase_currently_unavailable(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with 'we are currently unavailable' phrase."""
        transcription = "We are currently unavailable, please leave your details"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_detect_voicemail_phrase_after_the_tone(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with 'leave a message after the tone' phrase."""
        transcription = "Please leave a message after the tone and we will return your call"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    # Test case insensitivity

    @staticmethod
    def test_detect_voicemail_lowercase(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with uppercase text."""
        transcription = "YOU HAVE REACHED THE VOICEMAIL"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_detect_voicemail_mixed_case(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with mixed case text."""
        transcription = "PlEaSe LeAvE a MeSsAgE aFtEr ThE bEeP"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    # Test punctuation handling
    @staticmethod
    def test_detect_voicemail_with_punctuation(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with punctuation marks."""
        transcription = "Hello! You've reached the voicemail. Leave a message!"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_detect_voicemail_with_special_chars(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with special characters."""
        transcription = "Hi! You have reached: John's voicemail... Please, leave a message!"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    # Test non-voicemail scenarios

    @staticmethod
    def test_no_voicemail_live_person_greeting(rule_based_detector: VoicemailDetector) -> None:
        """Test that live person greeting is not detected as voicemail."""
        transcription = "Hello, this is John speaking. How can I help you?"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is False

    @staticmethod
    def test_no_voicemail_conversation(rule_based_detector: VoicemailDetector) -> None:
        """Test that normal conversation is not detected as voicemail."""
        transcription = "Yes, I can help you with that. What do you need?"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is False

    @staticmethod
    def test_no_voicemail_business_greeting(rule_based_detector: VoicemailDetector) -> None:
        """Test that business greeting is not detected as voicemail."""
        transcription = "Hello, ABC Company, this is Sarah. How may I direct your call?"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is False

    @staticmethod
    def test_no_voicemail_partial_match(rule_based_detector: VoicemailDetector) -> None:
        """Test that partial word matches don't trigger detection."""
        transcription = "I will be available tomorrow at noon to discuss"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is False

    # Test edge cases

    @staticmethod
    def test_detect_voicemail_empty_string(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with empty string."""
        transcription = ""
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is False

    @staticmethod
    def test_detect_voicemail_whitespace_only(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with whitespace only."""
        transcription = "   \n\t   "
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is False

    @staticmethod
    def test_detect_voicemail_multiple_patterns(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with multiple patterns in transcription."""
        transcription = "You have reached the voicemail. Leave a message after the beep. Thank you for calling."
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    # Test async wrapper method

    @staticmethod
    @pytest.mark.asyncio()
    async def test_detect_voicemail_async_wrapper_voicemail(rule_based_detector: VoicemailDetector) -> None:
        """Test async detect_voicemail method returns VoicemailDetectionResult for voicemail."""
        transcription = "You have reached the voicemail of Dr. Smith"
        result = await rule_based_detector.detect_voicemail(transcription)

        assert result is not None
        assert isinstance(result, VoicemailDetectionResult)
        assert result.is_voicemail is True

    @staticmethod
    @pytest.mark.asyncio()
    async def test_detect_voicemail_async_wrapper_not_voicemail(rule_based_detector: VoicemailDetector) -> None:
        """Test async detect_voicemail method returns VoicemailDetectionResult for live person."""
        transcription = "Hello, this is John speaking"
        result = await rule_based_detector.detect_voicemail(transcription)

        assert result is not None
        assert isinstance(result, VoicemailDetectionResult)
        assert result.is_voicemail is False

    @staticmethod
    @pytest.mark.asyncio()
    async def test_detect_voicemail_async_wrapper_empty(rule_based_detector: VoicemailDetector) -> None:
        """Test async detect_voicemail method handles empty transcription."""
        transcription = ""
        result = await rule_based_detector.detect_voicemail(transcription)

        assert result is None

    @staticmethod
    @pytest.mark.asyncio()
    async def test_detect_voicemail_async_wrapper_whitespace(rule_based_detector: VoicemailDetector) -> None:
        """Test async detect_voicemail method handles whitespace-only transcription."""
        transcription = "   \n\t   "
        result = await rule_based_detector.detect_voicemail(transcription)

        assert result is None

    # Test realistic voicemail scenarios

    @staticmethod
    def test_detect_voicemail_realistic_personal(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with realistic personal voicemail greeting."""
        transcription = (
            "Hi, you have reached John Doe. I'm unable to take your call right now. "
            "Please leave a message after the beep and I will get back to you as soon as possible."
        )
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_detect_voicemail_realistic_business(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with realistic business voicemail greeting."""
        transcription = (
            "Thank you for calling ABC Services. We are currently unavailable to take your call. "
            "Please leave a detailed message with your name and number and we will get back to you shortly."
        )
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_detect_voicemail_realistic_full_mailbox(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with realistic full mailbox message."""
        transcription = "The mailbox is full and cannot accept any messages at this time. Please try again later."
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_detect_voicemail_realistic_generic(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with generic voicemail system message."""
        transcription = (
            "The person you are trying to reach is not available. "
            "Please record your message after the tone. Press pound when finished."
        )
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True

    @staticmethod
    def test_no_voicemail_realistic_receptionist(rule_based_detector: VoicemailDetector) -> None:
        """Test that realistic receptionist greeting is not detected as voicemail."""
        transcription = (
            "Good afternoon, thank you for calling Medical Associates. "
            "This is Jennifer speaking. How may I help you today?"
        )
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is False

    @staticmethod
    def test_no_voicemail_realistic_callback(rule_based_detector: VoicemailDetector) -> None:
        """Test that callback acknowledgment is not detected as voicemail."""
        transcription = "Hi, I'm returning your call from earlier today. Is now a good time to talk?"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is False

    @staticmethod
    def test_real_call_from_uat(rule_based_detector: VoicemailDetector) -> None:
        """Test detection with real call transcription from UAT environment."""
        transcription = "to leave a message, wait for the tone if you want to leave your number, only press 1"
        result = rule_based_detector._detect_voicemail_rule_based(transcription)
        assert result is True
