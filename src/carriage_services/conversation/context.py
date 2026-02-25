from dataclasses import dataclass, field

from carriage_services.conversation.flows import Flow, QuestionFlow
from carriage_services.conversation.state import Message


@dataclass
class UnderstandingContext:
    """Context information for understanding user intent."""

    current_flow: Flow | None = None
    conversation_history: list[Message] = field(default_factory=lambda: [])
    available_flows: list[Flow] = field(
        default_factory=lambda: [QuestionFlow()]
    )  # Only flow that UnderstandingEngine can start

    @property
    def previous_bot_utterance(self) -> Message:
        """Get the most recent bot message from conversation history."""
        bot_messages = [message for message in self.conversation_history if message.role == "bot"]
        return bot_messages[-1] if bot_messages else Message(content="", role="bot")
