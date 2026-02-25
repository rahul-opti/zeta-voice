from datetime import datetime
from typing import Any

from pydantic import BaseModel


class Message(BaseModel):
    """Represents a message in the conversation."""

    content: str
    role: str
    intent_name: str = ""
    utterance_name: str = ""
    intro_content: str = ""


class ConversationState:
    """Manages the state of the entire conversation."""

    def __init__(self) -> None:
        self.lead_info: dict = {}
        self.conversation_history: list[Message] = []
        self.initial_date: datetime | None = None
        self.available_dates: list[datetime] = []

    def update_lead_info(self, **kwargs: Any) -> None:
        """Update lead information."""
        self.lead_info.update(kwargs)

    def set_calendar_data(self, initial_date: datetime | None, available_dates: list[datetime]) -> None:
        """Set calendar data for the conversation."""
        self.initial_date = initial_date
        self.available_dates = available_dates

    def add_to_history(
        self, message: str, role: str, intent_name: str = "", utterance_name: str = "", intro_content: str = ""
    ) -> None:
        """Add a message to the conversation history."""
        self.conversation_history.append(
            Message(
                content=message,
                role=role,
                intent_name=intent_name,
                utterance_name=utterance_name,
                intro_content=intro_content,
            )
        )

    def get_conversation_history(self) -> list[Message]:
        """Get the full conversation history."""
        return self.conversation_history.copy()
