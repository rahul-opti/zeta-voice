"""Unit test for neutralize_phrases function in booking flow.

This test calls the OpenAI client 100 times with the same prompt and asserts
that the neutralize_phrases function properly replaces forbidden phrases.
"""

import os
import sys
from datetime import date

import pytest
from jinja2 import Environment, FileSystemLoader
from litellm import completion
from tqdm import tqdm

from carriage_services.conversation.flows import BookingFlow
from carriage_services.conversation.models import BookingFlowMessage
from carriage_services.paths import BOOKING_FLOW_PROMPT_PATH
from carriage_services.settings import BookingFlowSettings
from carriage_services.utils.enums import BookingFlowPersona


class TestNeutralizePhrases:
    """Test suite for neutralize_phrases function."""

    @staticmethod
    def _get_test_prompt() -> str:
        """Generate the test prompt using the booking flow template."""
        prompt_template = Environment(loader=FileSystemLoader(searchpath="/"), autoescape=True).get_template(
            str(BOOKING_FLOW_PROMPT_PATH)
        )

        # Test data
        current_date = date(2026, 2, 2)  # Monday, February 02, 2026

        # Available dates
        available_dates = [
            "Thursday, February 12 at 9 AM",
            "Thursday, February 12 at 10 AM",
            "Thursday, February 12 at 11 AM",
            "Thursday, February 12 at 12 PM",
            "Thursday, February 12 at 1 PM",
            "Thursday, February 12 at 2 PM",
            "Thursday, February 12 at 3 PM",
            "Thursday, February 12 at 4 PM",
            "Friday, February 13 at 9 AM",
            "Friday, February 13 at 11 AM",
            "Friday, February 13 at 12 PM",
            "Friday, February 13 at 1 PM",
            "Friday, February 13 at 2 PM",
            "Friday, February 13 at 4 PM",
            "Monday, February 16 at 10 AM",
            "Monday, February 16 at 11 AM",
            "Monday, February 16 at 12 PM",
            "Monday, February 16 at 1 PM",
            "Monday, February 16 at 2 PM",
            "Monday, February 16 at 3 PM",
            "Monday, February 16 at 4 PM",
            "Tuesday, February 17 at 9 AM",
            "Tuesday, February 17 at 10 AM",
            "Tuesday, February 17 at 11 AM",
            "Tuesday, February 17 at 12 PM",
            "Tuesday, February 17 at 1 PM",
            "Tuesday, February 17 at 2 PM",
            "Tuesday, February 17 at 3 PM",
            "Tuesday, February 17 at 4 PM",
            "Wednesday, February 18 at 9 AM",
            "Wednesday, February 18 at 10 AM",
            "Wednesday, February 18 at 11 AM",
            "Wednesday, February 18 at 12 PM",
            "Wednesday, February 18 at 1 PM",
            "Wednesday, February 18 at 2 PM",
            "Wednesday, February 18 at 3 PM",
            "Wednesday, February 18 at 4 PM",
            "Thursday, February 19 at 9 AM",
            "Thursday, February 19 at 10 AM",
            "Thursday, February 19 at 11 AM",
            "Thursday, February 19 at 12 PM",
            "Thursday, February 19 at 1 PM",
            "Thursday, February 19 at 2 PM",
            "Thursday, February 19 at 3 PM",
            "Thursday, February 19 at 4 PM",
            "Friday, February 20 at 9 AM",
            "Friday, February 20 at 10 AM",
            "Friday, February 20 at 11 AM",
            "Friday, February 20 at 12 PM",
            "Friday, February 20 at 1 PM",
            "Friday, February 20 at 2 PM",
            "Friday, February 20 at 3 PM",
            "Friday, February 20 at 4 PM",
            "Monday, February 23 at 9 AM",
            "Monday, February 23 at 10 AM",
            "Monday, February 23 at 11 AM",
            "Monday, February 23 at 12 PM",
            "Monday, February 23 at 1 PM",
            "Monday, February 23 at 2 PM",
            "Monday, February 23 at 3 PM",
            "Monday, February 23 at 4 PM",
            "Tuesday, February 24 at 9 AM",
            "Tuesday, February 24 at 10 AM",
            "Tuesday, February 24 at 11 AM",
            "Tuesday, February 24 at 12 PM",
            "Tuesday, February 24 at 1 PM",
            "Tuesday, February 24 at 2 PM",
            "Tuesday, February 24 at 3 PM",
            "Tuesday, February 24 at 4 PM",
        ]

        initial_date = "Thursday, February 12 at 9 AM"
        booking_flow_persona = BookingFlowPersona.EMPATHETIC_AND_PROFESSIONAL.value

        # Example test conversation history
        conversation_history = [
            {
                "role": "bot",
                "content": "Hello. This is Ava from Carriage Services. \
            The reason for my call is you had previously signed up to discuss our preplanning services with our team. \
            Am I speaking to John Smith?",
                "intro_content": "",
            },
            {"role": "user", "content": "Yeah, that's me.", "intro_content": ""},
            {"role": "bot", "content": "Thank you.Would you like to come visit us on property?", "intro_content": ""},
            {"role": "user", "content": "Yeah, sure.", "intro_content": ""},
            {
                "role": "bot",
                "content": "Let's get your appointment scheduled. \
                    Would you like to schedule your appointment for Thursday, February twelfth at 9 AM?",
                "intro_content": "",
            },
            {"role": "user", "content": "Yeah, sounds good.", "intro_content": ""},
        ]

        prompt = prompt_template.render(
            user_message="",
            conversation_history=conversation_history,
            available_dates=available_dates,
            initial_date=initial_date,
            booking_flow_persona=booking_flow_persona,
            current_date=current_date,
        )

        return prompt

    @staticmethod
    def _get_forbidden_phrases() -> list[str]:
        """Get the list of forbidden phrases that should be neutralized."""
        return [
            "Excellent choice",
            "Fantastic choice",
            "Wonderful choice",
            "Great choice",
            "Excellent",
            "That works perfectly",
            "Perfect",
            "Wonderful",
            "Great",
            "Fantastic",
            "Phenomenal",
            "Outstanding",
            "Superb",
            "Brilliant",
            "Marvelous",
            "Terrific",
            "Splendid",
            "Exceptional",
            "Magnificent",
        ]

    @staticmethod
    @pytest.mark.skipif(
        os.getenv("RUN_NEUTRALIZE_TEST", "false").lower() != "true",
        reason="Set RUN_NEUTRALIZE_TEST=true to run this test",
    )
    def test_neutralize_phrases_100_calls() -> None:
        """Test that neutralize_phrases works correctly across 100 API calls."""
        prompt = TestNeutralizePhrases._get_test_prompt()
        booking_flow_settings = BookingFlowSettings()
        forbidden_phrases = TestNeutralizePhrases._get_forbidden_phrases()

        for iteration in tqdm(
            range(100), desc="Testing neutralize_phrases", unit="call", file=sys.stderr, dynamic_ncols=True
        ):
            response = completion(
                model=booking_flow_settings.BOOKING_FLOW_MODEL,
                messages=[{"content": prompt, "role": "user"}],
                response_format=BookingFlowMessage,
            )

            message = BookingFlowMessage.model_validate_json(response.choices[0].message.content)
            original_message = message.booking_response_message
            neutralized_message = BookingFlow._neutralize_phrases(original_message)

            # Assert that no forbidden phrases remain in the neutralized message
            neutralized_lower = neutralized_message.lower()
            for phrase in forbidden_phrases:
                phrase_lower = phrase.lower()
                assert phrase_lower not in neutralized_lower, (
                    f"Iteration {iteration + 1}: Forbidden phrase '{phrase}' found in neutralized message. "
                    f"Original: '{original_message}', Neutralized: '{neutralized_message}'"
                )
