import asyncio
from unittest.mock import MagicMock, patch

from fastapi import BackgroundTasks
from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from carriage_services.conversation.runner import Runner, StartCallRequest
from carriage_services.database import get_db
from carriage_services.database.models import Base
from carriage_services.settings import ConversationSettings, settings

# --- Test Setup ---
CONFIG = ConversationSettings()
START_REQUEST = StartCallRequest(
    to_number="test_number",
    lead_id="test_lead",
    handoff_number="test_number",
)


async def mock_anonymize_text(text: str) -> str:
    """A mock async function that returns the text as is, avoiding the slow spaCy model."""
    return text


def call_api(prompt: str, options: dict, context: dict) -> dict:
    """
    This function is the entry point called by promptfoo for each test case.
    It simulates an entire multi-turn conversation.
    """
    test_vars = context["vars"]
    conversation_turns = test_vars.get("conversation_turns", [])
    bot_responses = asyncio.run(simulate_conversation(conversation_turns))
    return {"output": bot_responses}


async def simulate_conversation(turns: list[dict]) -> list[str]:
    """
    Simulates a full conversation by instantiating the Runner and processing turns.
    """
    # Patch the anonymizer for the entire simulation to avoid loading spaCy.
    with patch("carriage_services.conversation.memory.anonymize_text", new=mock_anonymize_text):
        # Use an in-memory SQLite database for test isolation.
        test_engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
        TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
        Base.metadata.create_all(bind=test_engine)

        settings.calendar.DYNAMICS_ERP_BOOKING = False

        runner = Runner(CONFIG, voice_name="Maria")
        background_tasks = BackgroundTasks()

        # Patch the DB session provider to use our in-memory DB.
        with patch("carriage_services.database.session.SessionLocal", new=TestSessionLocal):
            db_session = next(get_db())

            await runner.initialize_conversation(
                initial_data=START_REQUEST, db=db_session, background_tasks=background_tasks
            )

            initial_bot_message = await runner.start_conversation(
                call_sid="test_call_sid", background_tasks=background_tasks
            )
            all_bot_responses = [" ".join(initial_bot_message)]

            for turn in turns:
                user_message = turn["user"]
                mock_llm_responses = turn.get("mock_llm_responses", [])

                with patch("litellm.completion", new_callable=MagicMock) as mock_completion:
                    mock_completion.side_effect = [
                        MagicMock(choices=[MagicMock(message=MagicMock(content=response))])
                        for response in mock_llm_responses
                    ]

                    bot_response_parts = await runner.handle_single_message(user_message, background_tasks)
                    bot_response = " ".join(bot_response_parts)
                    all_bot_responses.append(bot_response)

                    logger.info("--- Turn ---")
                    logger.info(f"USER: {user_message}")
                    logger.info(f"BOT: {bot_response}")
                    logger.info(f"LLM Calls Mocked: {mock_completion.call_count}")
                    logger.info(f"Flow Stack: {[f.name for f in runner.flow_stack.flows]}")

            return all_bot_responses
