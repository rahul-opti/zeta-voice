import asyncio
import os
import sys
import uuid

import click
from fastapi import BackgroundTasks
from loguru import logger

from carriage_services.conversation.runner import OutputType, Runner, StartCallRequest
from carriage_services.database import create_tables, get_db
from carriage_services.interface.terminal import TerminalClient
from carriage_services.settings import ConversationSettings

os.environ["ENABLE_PROFILING"] = "true"

logger.remove()
logger.add(sys.stderr, level="DEBUG")

create_tables()

start_conversation_request = StartCallRequest(
    to_number="terminal_session",
    lead_id=os.getenv("DYNAMICS_LEAD_ID", "terminal_user"),
    handoff_number="terminal",
)


async def run_terminal_conversation(runner: Runner, output_type: OutputType = OutputType.TEXT) -> None:
    """Run text-only conversation in command line mode."""
    terminal = TerminalClient()
    runner.is_running = True

    background_tasks = BackgroundTasks()

    db = next(get_db())
    db.rollback()

    await runner.initialize_conversation(
        initial_data=start_conversation_request, db=db, background_tasks=background_tasks, output_type=output_type
    )
    sid = str(uuid.uuid4())
    logger.info(f"Starting conversation with SID: {sid}")
    message = await runner.start_conversation(call_sid=sid, output_type=output_type, background_tasks=background_tasks)
    terminal.send_message(message)

    while runner.is_running and runner.turn_count < runner.config.MAX_TURNS:
        user_message_tuple = terminal.receive_message()
        if user_message_tuple:
            user_message, _ = user_message_tuple
            # For terminal input, confidence is always 1.0 (no speech-to-text involved)
            response_message = await runner.handle_single_message(
                user_message, confidence=1.0, output_type=output_type, background_tasks=background_tasks
            )
            if response_message:
                terminal.send_message(response_message)


@click.command()
@click.option("--output-type", type=click.Choice(OutputType), default=OutputType.TEXT)
def terminal_conversation(output_type: OutputType) -> None:
    """Run the terminal-based conversation system."""
    config = ConversationSettings()

    while input("Do you want to start a new conversation? (yes/no): ").strip().lower() in ("yes", "y"):
        runner = Runner(config, voice_name="Maria")
        try:
            asyncio.run(run_terminal_conversation(runner, output_type))
        except Exception as e:
            logger.error(f"An error occurred during conversation: {e}")
            raise


if __name__ == "__main__":
    terminal_conversation()
