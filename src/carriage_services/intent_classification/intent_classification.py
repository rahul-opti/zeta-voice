import enum

import pandas as pd
from jinja2 import Environment, FileSystemLoader
from litellm import completion
from loguru import logger
from pydantic import BaseModel

from carriage_services import paths
from carriage_services.conversation.context import UnderstandingContext
from carriage_services.conversation.flows import Flow, Response
from carriage_services.conversation.models import Action, BookingFlowAction, RegularFlowAction, RepetitionAction
from carriage_services.settings import settings


class PredefinedIntent(BaseModel):
    """Pydantic model representing a predefined intent (FAQ or objection) with examples and chatbot responses."""

    name_id: str
    name: str
    examples: list[str]
    chatbot_responses: list[str]


class IntentClassification:
    """
    A class for classifying user intents in conversation contexts.
    """

    def __init__(self) -> None:
        """
        Initialize the IntentClassifier.
        """
        self._model = settings.intent_classification.INTENT_CLASSIFICATION_MODEL
        self._question_model = settings.intent_classification.QUESTION_CLASSIFICATION_MODEL
        self._objection_model = settings.intent_classification.OBJECTION_CLASSIFICATION_MODEL
        self._temperature = settings.intent_classification.INTENT_CLASSIFICATION_TEMPERATURE
        self._api_key = settings.intent_classification.OPENAI_API_KEY
        self._available_faqs: list[PredefinedIntent] = []
        self._available_objections: list[PredefinedIntent] = []
        self._load_predefined_intents_from_csv(
            str(paths.INTENT_CLASSIFICATION_FAQS_PATH),
            str(paths.INTENT_CLASSIFICATION_OBJECTIONS_PATH),
        )
        self._setup_prompt_template(
            str(paths.INTENT_CLASSIFICATION_PROMPT_PATH),
            str(paths.QUESTION_CLASSIFICATION_PROMPT_PATH),
            str(paths.OBJECTION_CLASSIFICATION_PROMPT_PATH),
        )

    def _setup_prompt_template(
        self, intent_prompt_path: str, question_prompt_path: str, objection_prompt_path: str
    ) -> None:
        """Set up the Jinja2 templates for intent, question and objection classification prompts."""
        self._intent_prompt_template = Environment(
            loader=FileSystemLoader(searchpath="/"), autoescape=True
        ).get_template(intent_prompt_path)
        self._question_prompt_template = Environment(
            loader=FileSystemLoader(searchpath="/"), autoescape=True
        ).get_template(question_prompt_path)
        self._objection_prompt_template = Environment(
            loader=FileSystemLoader(searchpath="/"), autoescape=True
        ).get_template(objection_prompt_path)

    def _load_predefined_intents_from_csv(self, faqs_path: str, objections_path: str) -> None:
        """
        Load intent definitions from CSV files.

        Args:
            faqs_path: Path to the CSV file containing FAQ intents
            objections_path: Path to the CSV file containing objection intents
        """
        self._available_faqs = self._parse_predefined_intents(faqs_path)
        self._available_objections = self._parse_predefined_intents(objections_path)

    @staticmethod
    def _parse_predefined_intents(csv_file_path: str) -> list[PredefinedIntent]:
        """
        Parse predefined intents (FAQs and objections) from a CSV file into a list of PredefinedIntent objects.

        Args:
            csv_file_path (str): Path to the CSV file containing FAQs or objections

        Returns:
            List[PredefinedIntent]: List of parsed PredefinedIntent objects
        """
        df = pd.read_csv(csv_file_path)

        intents = []

        for _, row in df.iterrows():
            intent_name_id = row["name_id"]
            intent_name = row["name"]

            examples = []
            for col in df.columns:
                if col.startswith("examples_user_response"):
                    example = row[col]
                    if pd.notna(example) and str(example).strip() not in ["", "nan"]:
                        examples.append(str(example).strip())

            chatbot_responses = []
            for col in df.columns:
                if col.startswith("example_chatbot_response"):
                    example = row[col]
                    if pd.notna(example) and str(example).strip() not in ["", "nan"]:
                        chatbot_responses.append(str(example).strip())

            intent = PredefinedIntent(
                name_id=intent_name_id, name=intent_name, examples=examples, chatbot_responses=chatbot_responses
            )

            intents.append(intent)

        return intents

    def classify_intent(self, user_message: str, context: UnderstandingContext) -> Action:
        """
        Classify intent of the user message and return action to be taken.

        Args:
            user_message (str): User message to classify intent for
            context (UnderstandingContext): Context information for classifying user intent

        Returns:
            Action: Action to be taken based on the user intent
        """
        global_slots = Flow.get_global_slots()

        prompt = self._intent_prompt_template.render(
            user_message=user_message,
            current_flow=context.current_flow,
            global_slots=global_slots,
            available_flows=context.available_flows,
            conversation_history=context.conversation_history[-settings.conversation.LLM_ANALYZED_TURNS :]
            if context.conversation_history
            else [],
        )
        prompt = "\n".join(line.strip() for line in prompt.split("\n") if line.strip())
        logger.info(f"Rendered prompt: {prompt}")

        if context.current_flow and context.current_flow.name == "booking_flow":
            response_format = BookingFlowAction
        else:
            response_format = RegularFlowAction  # type: ignore

        response = completion(
            model=self._model,
            messages=[{"content": prompt, "role": "user"}],
            response_format=response_format,
            temperature=self._temperature,
        )

        try:
            action = response_format.model_validate_json(response.choices[0].message.content)
            return action
        except ValueError as e:
            logger.error(f"Error validating response: {e}")
            repetition_action = RepetitionAction(user_message="Invalid response format")
            return Action(action=repetition_action)

    def classify_question(self, user_message: str) -> Response:
        """
        Return chatbot response for the user question.

        Args:
            user_message (str): User question to return chatbot response for

        Returns:
            Response: Response containing the question name ID and chatbot response
        """
        prompt = self._question_prompt_template.render(
            user_message=user_message,
            available_faqs=self._available_faqs,
        )

        QuestionCategoryEnum = enum.Enum("QuestionCategoryEnum", {faq.name: faq.name for faq in self._available_faqs})  # type: ignore

        response_category_name, chatbot_response = self._classify_response(
            user_message, prompt, QuestionCategoryEnum, self._question_model
        )  # type: ignore

        logger.info(f"User question categorized as: {response_category_name}")

        faq_name_id = [faq.name_id for faq in self._available_faqs if faq.name == response_category_name][0]

        response = Response(
            intent_name=faq_name_id,
            utterance_name="example_chatbot_response_1",
            utterance_content=chatbot_response,
        )

        return response

    def classify_objection(self, user_message: str) -> Response:
        """
        Return chatbot response for the user objection.

        Args:
            user_message (str): User objection to return chatbot response for

        Returns:
            Response: Response containing the objection name ID and chatbot response
        """
        prompt = self._objection_prompt_template.render(
            user_message=user_message, available_objections=self._available_objections
        )

        ObjectionCategoryEnum = enum.Enum(  # type: ignore
            "ObjectionCategoryEnum", {objection.name: objection.name for objection in self._available_objections}
        )

        response_category_name, chatbot_response = self._classify_response(
            user_message, prompt, ObjectionCategoryEnum, self._objection_model
        )  # type: ignore

        logger.info(f"User objection categorized as: {response_category_name}")

        objection_name_id = [
            objection.name_id for objection in self._available_objections if objection.name == response_category_name
        ][0]

        response = Response(
            intent_name=objection_name_id,
            utterance_name="example_chatbot_response_1",
            utterance_content=chatbot_response,
        )

        return response

    def _classify_response(
        self, user_message: str, prompt: str, category_enum: type[enum.Enum], model: str
    ) -> tuple[str, str]:
        from pydantic import create_model

        Category = create_model("Category", category=(category_enum, ...))  # type: ignore

        response = completion(
            model=model,
            messages=[{"content": prompt, "role": "user"}],
            response_format=Category,
            temperature=self._temperature,
        )

        response_category = Category.model_validate_json(response.choices[0].message.content)

        if category_enum.__name__ == "ObjectionCategoryEnum":
            all_chatbot_responses = self._available_objections
        elif category_enum.__name__ == "QuestionCategoryEnum":
            all_chatbot_responses = self._available_faqs
        else:
            raise ValueError(f"Unknown category enum: {category_enum}")

        response_category_name = response_category.category.value  # type: ignore
        chatbot_response = [
            chatbot_response
            for chatbot_response in all_chatbot_responses
            if chatbot_response.name == response_category_name
        ][0].chatbot_responses[0]

        return response_category_name, chatbot_response
