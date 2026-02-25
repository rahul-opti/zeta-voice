from loguru import logger

from carriage_services.interface.base import Interface


class TerminalClient(Interface):
    """Conversation engine for terminal-based conversations."""

    def __init__(self) -> None:
        super().__init__()

    @staticmethod
    def send_message(
        messages: list[str],
        call_sid: str = "",
        is_running: bool = True,
        barge_in: bool = True,
    ) -> str:
        """Send a message to the user via terminal output."""
        message = " ".join(messages)
        logger.debug(f"BOT: {message}")
        return message

    @staticmethod
    def receive_message(form: dict | None = None) -> tuple[str, float] | None:
        """Receive a message from the user via terminal input."""
        try:
            user_input = input("\nYou: ").strip()
            logger.debug(f"USER: {user_input}")
            if user_input.lower() in ["quit", "exit", "bye", "goodbye"]:
                return user_input, 1.0

            if user_input:
                return user_input, 1.0
            return None
        except (EOFError, KeyboardInterrupt):
            return None
