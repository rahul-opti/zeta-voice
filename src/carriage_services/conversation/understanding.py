from dotenv import load_dotenv

from carriage_services.conversation.context import UnderstandingContext
from carriage_services.conversation.flows import Response
from carriage_services.conversation.models import Action
from carriage_services.intent_classification.intent_classification import IntentClassification

load_dotenv()


class OpenAIUnderstandingEngine:
    """Understanding engine using OpenAI API for intent classification."""

    def __init__(self) -> None:
        self.intent_classification = IntentClassification()

    def understand(self, user_message: str, context: UnderstandingContext) -> Action:
        """Use intent classification service to understand user intent."""
        return self.intent_classification.classify_intent(user_message, context)

    def understand_question(self, user_message: str) -> Response:
        """Use intent classification service to understand user question."""
        return self.intent_classification.classify_question(user_message)

    def understand_objection(self, user_message: str) -> Response:
        """Use intent classification service to understand user objection."""
        return self.intent_classification.classify_objection(user_message)
