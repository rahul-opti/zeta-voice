from abc import ABC, abstractmethod


class Interface(ABC):
    """Abstract base class for conversation engines."""

    @abstractmethod
    def send_message(
        self,
        messages: list[str],
        call_sid: str = "",
        is_running: bool = True,
        barge_in: bool = True,
    ) -> str:
        """Send a message to the user."""
        pass

    @abstractmethod
    def receive_message(self, form: dict | None = None) -> tuple[str, float] | None:
        """Receive a message from the user. May return just a string or a tuple of (message, confidence)."""
        pass
