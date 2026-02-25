import tempfile
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from carriage_services.conversation.context import UnderstandingContext
from carriage_services.conversation.models import Action
from carriage_services.intent_classification.intent_classification import (
    IntentClassification,
)


@pytest.fixture()
def mock_settings():
    """Mock settings for testing."""
    with patch("carriage_services.intent_classification.intent_classification.settings") as mock:
        mock.intent_classification.INTENT_CLASSIFICATION_MODEL = "gpt-4o-mini"
        mock.intent_classification.QUESTION_CLASSIFICATION_MODEL = "gpt-4o-mini"
        mock.intent_classification.OBJECTION_CLASSIFICATION_MODEL = "gpt-4o-mini"
        mock.intent_classification.INTENT_CLASSIFICATION_TEMPERATURE = 0.05
        mock.intent_classification.OPENAI_API_KEY = "test-api-key"
        mock.conversation.LLM_ANALYZED_TURNS = 5
        yield mock


@pytest.fixture()
def mock_paths():
    """Mock paths for testing."""
    with patch("carriage_services.intent_classification.intent_classification.paths") as mock_paths:
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            mock_paths.INTENT_CLASSIFICATION_FAQS_PATH = f.name
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            mock_paths.INTENT_CLASSIFICATION_OBJECTIONS_PATH = f.name
        with tempfile.NamedTemporaryFile(suffix=".j2", delete=False) as f:
            mock_paths.INTENT_CLASSIFICATION_PROMPT_PATH = f.name
        with tempfile.NamedTemporaryFile(suffix=".j2", delete=False) as f:
            mock_paths.QUESTION_CLASSIFICATION_PROMPT_PATH = f.name
        with tempfile.NamedTemporaryFile(suffix=".j2", delete=False) as f:
            mock_paths.OBJECTION_CLASSIFICATION_PROMPT_PATH = f.name
        yield mock_paths


@pytest.fixture()
def sample_faqs_csv():
    """Create a sample FAQs CSV file for testing."""
    data = {
        "name_id": ["do_not_call_me_again", "are_you_a_real_person"],
        "name": ["Do not call me again", "Are you a real person?"],
        "examples_user_response_1": ["Put me on the do not call list.", "Are you a real person?"],
        "examples_user_response_2": ["Do not call me again.", "Are you a human?"],
        "examples_user_response_3": ["", ""],
        "example_chatbot_response_1": ["I understand.", "I am an AI assistant."],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        df = pd.DataFrame(data)
        df.to_csv(f.name, index=False)
        yield f.name


@pytest.fixture()
def sample_objections_csv():
    """Create a sample objections CSV file for testing."""
    data = {
        "name_id": ["discomfort_with_the_topic", "financial_concerns"],
        "name": ["Discomfort with the Topic", "Financial Concerns"],
        "examples_user_response_1": ["I don't want to talk about death.", "I can't afford this."],
        "examples_user_response_2": ["This is too morbid.", "It's too expensive."],
        "examples_user_response_3": ["", ""],
        "example_chatbot_response_1": ["Sure, I understand.", "We have payment plans."],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        df = pd.DataFrame(data)
        df.to_csv(f.name, index=False)
        yield f.name


@pytest.fixture()
def sample_prompt_templates():
    """Create sample prompt template files for testing."""
    intent_template = """
    User message: {{ user_message }}
    Current flow: {{ current_flow }}
    Global slots: {{ global_slots }}
    Available flows: {{ available_flows }}
    Conversation history: {{ conversation_history }}
    Action: {{ action }}
    """

    question_template = """
    User message: {{ user_message }}
    Available FAQs: {{ available_faqs }}
    """

    objection_template = """
    User message: {{ user_message }}
    Available objections: {{ available_objections }}
    """

    templates = {}
    for name, content in [
        ("intent", intent_template),
        ("question", question_template),
        ("objection", objection_template),
    ]:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".j2", delete=False) as f:
            f.write(content)
            templates[name] = f.name

    return templates


@pytest.fixture()
def mock_understanding_context():
    """Create a mock UnderstandingContext for testing."""
    context = Mock(spec=UnderstandingContext)
    context.current_flow = None
    context.conversation_history = []
    context.available_flows = []
    return context


class TestIntentClassification:
    """Test the IntentClassification class."""

    def test_init_success(  # noqa: PLR6301
        self,
        mock_settings: Mock,
        mock_paths: Mock,
        sample_faqs_csv: str,
        sample_objections_csv: str,
        sample_prompt_templates: dict,
    ):
        """Test successful initialization of IntentClassification."""
        mock_paths.INTENT_CLASSIFICATION_FAQS_PATH = sample_faqs_csv
        mock_paths.INTENT_CLASSIFICATION_OBJECTIONS_PATH = sample_objections_csv
        mock_paths.INTENT_CLASSIFICATION_PROMPT_PATH = sample_prompt_templates["intent"]
        mock_paths.QUESTION_CLASSIFICATION_PROMPT_PATH = sample_prompt_templates["question"]
        mock_paths.OBJECTION_CLASSIFICATION_PROMPT_PATH = sample_prompt_templates["objection"]

        classifier = IntentClassification()

        assert classifier._model == "gpt-4o-mini"
        assert classifier._api_key == "test-api-key"
        assert len(classifier._available_faqs) == 2
        assert len(classifier._available_objections) == 2

    def test_parse_predefined_intents_success(self, sample_faqs_csv: str):  # noqa: PLR6301
        """Test parsing predefined intents from CSV file."""
        intents = IntentClassification._parse_predefined_intents(sample_faqs_csv)

        assert len(intents) == 2

        assert intents[0].name == "Do not call me again"
        assert intents[0].examples == ["Put me on the do not call list.", "Do not call me again."]

        assert intents[1].name == "Are you a real person?"
        assert intents[1].examples == ["Are you a real person?", "Are you a human?"]

    @patch("carriage_services.intent_classification.intent_classification.completion")
    @patch("carriage_services.conversation.flows.Flow.get_global_slots")
    def test_classify_intent_success(  # noqa: PLR6301
        self,
        mock_get_global_slots: Mock,
        mock_completion: Mock,
        mock_settings: Mock,
        mock_paths: Mock,
        sample_faqs_csv: str,
        sample_objections_csv: str,
        sample_prompt_templates: dict,
        mock_understanding_context: Mock,
    ):
        """Test successful intent classification."""
        mock_paths.INTENT_CLASSIFICATION_FAQS_PATH = sample_faqs_csv
        mock_paths.INTENT_CLASSIFICATION_OBJECTIONS_PATH = sample_objections_csv
        mock_paths.INTENT_CLASSIFICATION_PROMPT_PATH = sample_prompt_templates["intent"]
        mock_paths.QUESTION_CLASSIFICATION_PROMPT_PATH = sample_prompt_templates["question"]
        mock_paths.OBJECTION_CLASSIFICATION_PROMPT_PATH = sample_prompt_templates["objection"]

        mock_get_global_slots.return_value = {}

        mock_response = Mock()
        mock_response.choices = [
            Mock(
                message=Mock(
                    content=(
                        '{"action": {"action_type": "set_slot", "flow_name": "intro_flow", '
                        '"slot_name": "confirm_identity", "slot_value": "True"}}'
                    )
                )
            )
        ]
        mock_completion.return_value = mock_response

        classifier = IntentClassification()
        result = classifier.classify_intent("Hello", mock_understanding_context)

        assert isinstance(result, Action)
        assert result.action.action_type == "set_slot"
        mock_completion.assert_called_once()

    @patch("carriage_services.intent_classification.intent_classification.completion")
    def test_classify_question_success(  # noqa: PLR6301
        self,
        mock_completion: Mock,
        mock_settings: Mock,
        mock_paths: Mock,
        sample_faqs_csv: str,
        sample_objections_csv: str,
        sample_prompt_templates: dict,
    ):
        """Test successful question classification."""
        mock_paths.INTENT_CLASSIFICATION_FAQS_PATH = sample_faqs_csv
        mock_paths.INTENT_CLASSIFICATION_OBJECTIONS_PATH = sample_objections_csv
        mock_paths.INTENT_CLASSIFICATION_PROMPT_PATH = sample_prompt_templates["intent"]
        mock_paths.QUESTION_CLASSIFICATION_PROMPT_PATH = sample_prompt_templates["question"]
        mock_paths.OBJECTION_CLASSIFICATION_PROMPT_PATH = sample_prompt_templates["objection"]

        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content='{"category": "Do not call me again"}'))]
        mock_completion.return_value = mock_response

        classifier = IntentClassification()
        result = classifier.classify_question("Put me on the do not call list")

        assert result.utterance_content == "I understand."
        mock_completion.assert_called_once()

    @patch("carriage_services.intent_classification.intent_classification.completion")
    def test_classify_objection_success(  # noqa: PLR6301
        self,
        mock_completion: Mock,
        mock_settings: Mock,
        mock_paths: Mock,
        sample_faqs_csv: str,
        sample_objections_csv: str,
        sample_prompt_templates: dict,
    ):
        """Test successful objection classification."""
        mock_paths.INTENT_CLASSIFICATION_FAQS_PATH = sample_faqs_csv
        mock_paths.INTENT_CLASSIFICATION_OBJECTIONS_PATH = sample_objections_csv
        mock_paths.INTENT_CLASSIFICATION_PROMPT_PATH = sample_prompt_templates["intent"]
        mock_paths.QUESTION_CLASSIFICATION_PROMPT_PATH = sample_prompt_templates["question"]
        mock_paths.OBJECTION_CLASSIFICATION_PROMPT_PATH = sample_prompt_templates["objection"]

        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content='{"category": "Discomfort with the Topic"}'))]
        mock_completion.return_value = mock_response

        classifier = IntentClassification()
        result = classifier.classify_objection("I don't want to talk about death")

        assert result.utterance_content == "Sure, I understand."
        mock_completion.assert_called_once()
