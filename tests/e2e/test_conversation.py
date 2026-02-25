from dataclasses import dataclass

import pandas as pd
import pytest
from fastapi import BackgroundTasks
from loguru import logger
from sqlalchemy.orm import Session

from carriage_services.conversation.runner import Runner, StartCallRequest
from carriage_services.settings import ConversationSettings, settings


@pytest.fixture(autouse=True)
def _patch_settings_for_non_dynamics(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fixture to disable Dynamics ERP booking for the duration of a test."""
    monkeypatch.setattr(settings.calendar, "DYNAMICS_ERP_BOOKING", False)


@dataclass
class ConversationTestCase:
    """Test case for conversation flow testing."""

    name: str
    user_messages: list[str]
    expected_slots: list[str]


CONVERSATION_TEST_CASES = [
    ConversationTestCase(
        name="resignation_flow_accept_all_scenario",
        user_messages=[
            "Hello, no that's not me.",
            "I don't think we need to plan ahead; we can deal with it later.",
            "No, thanks.",
            "No, that's not necessary.",
            "I want to attend to a seminar.",
            "Goodbye!",
        ],
        expected_slots=[
            "accept_preplanning",
            "offer_rebuttal",
            "user_wants_human_transfer",
            "attend_seminar",
            "accept_seminar_list",
            "resignation_goodbye",
        ],
    ),
    ConversationTestCase(
        name="intro_flow_with_repetition",
        user_messages=[
            "Yes, it's me.",
            "Hhasdh dfsjfsj.",
            "Not really, I don't need it.",
            "No, thanks.",
        ],
        expected_slots=[
            "accept_appointment",
            "accept_appointment",
            "offer_rebuttal",
            "user_wants_human_transfer",
        ],
    ),
    ConversationTestCase(
        name="question_flow_scenario",
        user_messages=[
            "Yes, that's me indeed.",
            "What's the cost of a funeral?",
        ],
        expected_slots=[
            "accept_appointment",
            "question_answered",
        ],
    ),
]


@pytest.mark.asyncio()
@pytest.mark.parametrize("test_case", CONVERSATION_TEST_CASES, ids=[case.name for case in CONVERSATION_TEST_CASES])
async def test_conversation(
    test_case: ConversationTestCase,
    utterances: pd.DataFrame,
    objection_utterances: pd.DataFrame,
    question_utterances: pd.DataFrame,
    test_db_session: Session,
) -> None:
    """
    Test the conversation runner with a mock database session.

    This test initializes a conversation, starts it, and handles a user message,
    verifying that the response is as expected.
    """
    config = ConversationSettings()
    runner = Runner(config, voice_name="Maria")

    start_conversation_request = StartCallRequest(
        to_number="test_number", user_id="test_user", handoff_number="test_number"
    )

    background_tasks = BackgroundTasks()
    await runner.initialize_conversation(
        initial_data=start_conversation_request, db=test_db_session, background_tasks=background_tasks
    )
    initial_message = await runner.start_conversation(call_sid="test_call_sid", background_tasks=background_tasks)
    logger.info(f"BOT: {initial_message}")

    assert initial_message is not None
    assert isinstance(initial_message, list)
    assert isinstance(initial_message[0], str)

    user_messages = test_case.user_messages.copy()
    expected_slots = test_case.expected_slots.copy()

    while user_messages:
        user_message = user_messages.pop(0)
        expected_slot = expected_slots.pop(0) if expected_slots else None

        logger.info(f"USER: {user_message}")
        response_message = await runner.handle_single_message(user_message, background_tasks)
        logger.info(f"BOT: {response_message}")
        assert response_message is not None
        assert isinstance(response_message, list)
        assert isinstance(response_message[0], str)

        if expected_slot == "offer_rebuttal":
            expected_message = _get_correct_objection_utterance(objection_utterances)
            assert (
                response_message[0] == expected_message
            ), f"Expected objection utterance: {expected_message} but got: {response_message[0]}"
        elif expected_slot == "question_answered":
            expected_message = _get_correct_question_utterance(question_utterances)
            assert (
                response_message[0] == expected_message
            ), f"Expected question utterance: {expected_message} but got: {response_message[0]}"
        elif expected_slot:
            try:
                if len(response_message) > 1:
                    bot_slot = _get_bot_slot(response_message[1], utterances)
                else:
                    bot_slot = _get_bot_slot(response_message[0], utterances)
            except IndexError as e:
                raise AssertionError(
                    f"Expected slot '{expected_slot}' but got bot responses '{response_message}' "
                    f"for user message: {user_message}"
                ) from e
            assert (
                bot_slot == expected_slot
            ), f"Expected slot '{expected_slot}' but got '{bot_slot}' for user message: {user_message}"


def _get_bot_slot(bot_message: str, utterances: pd.DataFrame) -> str:
    """
    Extract the slot name from the bot's response message based on the utterances DataFrame.

    Args:
        bot_message (str): The message from the bot.
        utterances (pd.DataFrame): DataFrame containing utterances with slot names.

    Returns:
        str: The slot name corresponding to the bot's message.
    """
    mask = utterances.apply(lambda row: row.astype(str).str.contains(bot_message[:30], case=False, na=False)).any(
        axis=1
    )
    return utterances.loc[mask, "slot_name"].tolist()[0]


def _get_correct_objection_utterance(objection_utterances: pd.DataFrame) -> str:
    return objection_utterances[objection_utterances["name"] == "Belief that it's Not Necessary"].iloc[0][
        "example_chatbot_response_1"
    ]


def _get_correct_question_utterance(question_utterances: pd.DataFrame) -> str:
    return question_utterances[question_utterances["name"] == "Pricing request"].iloc[0]["example_chatbot_response_1"]
