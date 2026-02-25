import json
from asyncio import Event
from asyncio import sleep as asleep
from datetime import datetime
from enum import Enum
from typing import Any, Literal, cast
from uuid import UUID

from fastapi import BackgroundTasks
from loguru import logger
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from carriage_services.conversation import calendar_api
from carriage_services.conversation.calendar_api import (
    mock_calendar_api_get_available_dates,
    mock_calendar_api_get_initial_date_slot,
)
from carriage_services.conversation.context import UnderstandingContext
from carriage_services.conversation.flows import (
    FLOW_REGISTRY,
    BookingFlow,
    Flow,
    FlowStack,
    IntroFlow,
    QuestionFlow,
    RebuttalFlow,
    RepetitionFlow,
    ResignationFlow,
)
from carriage_services.conversation.memory import MemoryService
from carriage_services.conversation.models import (
    Action,
    ContinueAction,
    RepetitionAction,
    SetSlotAction,
    StartFlowAction,
)
from carriage_services.conversation.rephrase import Rephraser
from carriage_services.conversation.rule_based_english_classifier import RuleBasedEnglishClassifier
from carriage_services.conversation.state import (
    ConversationState,
    Message,
)
from carriage_services.conversation.understanding import OpenAIUnderstandingEngine
from carriage_services.database.actions import upsert_conversation_context
from carriage_services.paths import INTRO_MESSAGES_PATH
from carriage_services.question_classification.question_classification import QuestionClassification
from carriage_services.settings import ConversationSettings, settings
from carriage_services.tts.tts import create_tts_service, get_voice_config
from carriage_services.utils import ConversationStatus, fetch_lead_data, profile_method
from carriage_services.utils.enums import LeadStatus
from carriage_services.utils.handle_errors import handle_errors
from carriage_services.utils.helpers import (
    Response,
    convert_numbers_to_string_digits,
    generate_intro_message_description,
)
from carriage_services.voicemail_detection.voicemail_detection import VoicemailDetector


class ChatbotResponseType(str, Enum):
    """Type of chatbot response."""

    STATIC = "static"
    DYNAMIC = "dynamic"


def _create_intro_message_version_enum():  # type: ignore  # noqa: ANN202
    """Create IntroMessageVersion enum from JSON configuration."""
    with open(INTRO_MESSAGES_PATH) as f:
        intro_messages_data = json.load(f)

    enum_members = {}
    for key in intro_messages_data["versions"]:
        enum_members[key.upper()] = key

    return Enum("IntroMessageVersion", enum_members, type=str)


IntroMessageVersion = _create_intro_message_version_enum()


def _create_voice_name_enum():  # type: ignore  # noqa: ANN202
    """Create VoiceName enum from elevenlabs_voices.json configuration."""
    from carriage_services.tts.tts import get_available_voice_names  # noqa: PLC0415

    voice_names = get_available_voice_names()
    enum_members = {name.upper(): name for name in voice_names}
    return Enum("VoiceName", enum_members, type=str)


VoiceName = _create_voice_name_enum()


class ChatbotResponse(BaseModel):
    """Chatbot response."""

    response_type: ChatbotResponseType
    texts: list[tuple[Literal["intro", "core"], str]]
    urls: list[tuple[Literal["intro", "core"], str]]
    intent_name: str = ""
    utterance_name: str = ""


class StartCallRequest(BaseModel):
    """Defines the request body for starting a call."""

    to_number: str = Field(..., description="The destination phone number in E.164 format.")
    user_id: str | None = Field(None, description="An optional identifier for the user associated with the call.")
    lead_id: str | None = Field(None, description="The unique identifier for the lead in the CRM.")
    handoff_number: str = Field(..., description="A PSTN number in E.164 format to transfer the call to.")
    funeral_home_name: str | None = Field(
        None,
        description="Optional name of the funeral home to be used in the conversation. "
        "If not provided, will use the default from lead data.",
    )
    funeral_home_address: str | None = Field(
        None,
        description="Optional address of the funeral home to be used in the conversation. "
        "If not provided, will use the default from lead data.",
    )
    user_name: str | None = Field(
        None,
        description="Optional name of the user to be used in the conversation. "
        "If not provided, will use the default from lead data.",
    )
    intro_message_version: IntroMessageVersion | None = Field(  # type: ignore[valid-type]
        None,
        description=generate_intro_message_description(str(INTRO_MESSAGES_PATH)),
    )

    @model_validator(mode="after")
    def check_id_fields(self) -> "StartCallRequest":
        """Ensure either user_id or lead_id is provided based on settings."""
        if settings.calendar.DYNAMICS_ERP_BOOKING:
            if not self.lead_id:
                raise ValueError("'lead_id' is required when DYNAMICS_ERP_BOOKING is enabled.")
        elif not self.user_id:
            # For backward compatibility, we can allow user_id to be optional if not using Dynamics
            pass
        return self


class OutputType(str, Enum):
    """Output type for the conversation."""

    TEXT = "text"
    URL = "url"


class Runner:
    """Main conversation runner that orchestrates the entire system."""

    def __init__(self, config: ConversationSettings, voice_name: str) -> None:
        self.config = config
        self.flow_stack = FlowStack()
        self.conversation_state = ConversationState()
        self.understanding_engine = OpenAIUnderstandingEngine()
        self.rule_based_english_classifier = RuleBasedEnglishClassifier()
        self.question_classifier = QuestionClassification()
        self.tts_service = create_tts_service(voice_name)
        self.is_running = False
        self.turn_count = 0
        self.conversation_id: UUID
        self.memory: MemoryService
        self.transfer_to_human = False
        self.rephraser = Rephraser()
        voice_config = get_voice_config(voice_name)
        self.voice_name = voice_name
        self.bot_name = voice_config["name"]
        self.handoff_number: str = ""
        self.filler_word_counter = 0
        self.no_transcription_count = 0
        self.initial_message_generated = False
        self.initial_message_object: ChatbotResponse | None = None
        self.first_message_sent_time: datetime | None = None
        self.initialization_event = Event()
        self.intro_message_version: IntroMessageVersion | None = None  # type: ignore

    def _get_full_context(self) -> dict[str, Any]:
        """Gathers the entire current state of the runner into a dictionary."""
        serializable_history = [msg.model_dump() for msg in self.conversation_state.get_conversation_history()]

        flow_stack_names = [flow.name for flow in self.flow_stack.flows]

        all_slots: dict[str, Any] = {}
        if self.flow_stack.current_flow:
            try:
                all_slots = {name: slot.model_dump() for name, slot in self.flow_stack.current_flow.slots.items()}
            except Exception:
                all_slots = {
                    name: {"value": str(slot.value)} for name, slot in self.flow_stack.current_flow.slots.items()
                }

        context = {
            "conversation_id": str(self.conversation_id),
            "turn_count": self.turn_count,
            "is_running": self.is_running,
            "voice_name": self.voice_name,
            "bot_name": self.bot_name,
            "intro_message_version": self.intro_message_version.value if self.intro_message_version else None,  # type: ignore
            "conversation_state": {
                "lead_info": self.conversation_state.lead_info,
                "conversation_history": serializable_history,
                "initial_date": self.conversation_state.initial_date,
                "available_dates": self.conversation_state.available_dates,
            },
            "flow_stack": flow_stack_names,
            "all_slots": all_slots,
        }
        return context

    def _update_context_in_db(self) -> None:
        """Helper to gather and persist the full context to the database."""
        full_context = self._get_full_context()
        upsert_conversation_context(self.memory.db, self.conversation_id, full_context)

    async def initialize_conversation(
        self,
        initial_data: StartCallRequest,
        db: Session,
        background_tasks: BackgroundTasks,
        output_type: OutputType = OutputType.TEXT,
    ) -> None:
        """Initialize the conversation by pre-fetching required data and saving user data."""
        logger.info("Pre-fetching conversation data...")

        Flow.init_global_slots()

        user_id_for_db: str | None = None
        if settings.calendar.DYNAMICS_ERP_BOOKING:
            if not initial_data.lead_id:
                raise ValueError("Cannot initialize conversation: lead_id is missing for Dynamics ERP booking.")
            lead_data = await calendar_api.get_lead_details(initial_data.lead_id)
            if not lead_data:
                raise ValueError(f"Could not retrieve lead details for lead ID: {initial_data.lead_id}")

            if initial_data.funeral_home_name:
                lead_data["funeral_home_name"] = initial_data.funeral_home_name
            if initial_data.funeral_home_address:
                lead_data["funeral_home_address"] = initial_data.funeral_home_address
            if initial_data.user_name:
                lead_data["user_name"] = initial_data.user_name

            converted_lead_data = convert_numbers_to_string_digits(lead_data)
            self.conversation_state.update_lead_info(**converted_lead_data)

            calendar_id = lead_data.get("calendar_id")
            if not calendar_id:
                logger.error(f"Could not find calendar_id for lead {initial_data.lead_id}")
                available_dates = []
            else:
                available_dates = await calendar_api.get_available_dates(
                    calendar_id=calendar_id, lead_id=initial_data.lead_id
                )
            initial_date = calendar_api.get_initial_date_slot(available_dates)
            user_id_for_db = initial_data.lead_id
        else:
            lead_data = fetch_lead_data()
            if initial_data.funeral_home_name:
                lead_data["funeral_home_name"] = initial_data.funeral_home_name
            if initial_data.funeral_home_address:
                lead_data["funeral_home_address"] = initial_data.funeral_home_address
            if initial_data.user_name:
                lead_data["user_name"] = initial_data.user_name

            self.conversation_state.update_lead_info(**lead_data)
            initial_date = mock_calendar_api_get_initial_date_slot()
            available_dates = mock_calendar_api_get_available_dates()
            user_id_for_db = initial_data.user_id

        self.conversation_state.set_calendar_data(initial_date, available_dates)
        logger.info(f"Initialized calendar data - Initial date: {initial_date}")
        logger.info(f"Available dates: {available_dates}")

        self.memory = MemoryService(db)
        conversation_db = self.memory.store_conversation(
            initial_data.to_number, user_id_for_db, initial_data.handoff_number
        )
        self.conversation_id = conversation_db.id
        self.handoff_number = initial_data.handoff_number
        self.intro_message_version = initial_data.intro_message_version
        self._update_context_in_db()

        logger.info("Conversation initialized successfully")
        await self._pregenerate_initial_utterance(output_type, background_tasks=background_tasks)

        # Signal that initialization is complete
        self.initialization_event.set()

    async def _pregenerate_initial_utterance(self, output_type: OutputType, background_tasks: BackgroundTasks) -> None:
        logger.info("Started getting pre-generated initial utterance")
        self.initial_message_generated = True

        # Pre-generate the initial utterance for both output types in the background
        # This will be used when start_conversation is called
        self.start_flow("intro_flow")
        self.initial_message_object = await self._get_next_utterance(
            context=UnderstandingContext(),
            user_message="",
            output_type=output_type,
            background_tasks=background_tasks,
        )
        # Reset the flow stack as it will be re-initialized in start_conversation
        self.flow_stack = FlowStack()
        self.is_running = False

        logger.info("Finished pre-generating initial utterance")

    @profile_method()
    async def start_conversation(
        self, call_sid: str, background_tasks: BackgroundTasks, output_type: OutputType = OutputType.TEXT
    ) -> list[str]:
        """Pre-fetch data, initialize conversation, and generate first message."""
        decorated_method = handle_errors(self.memory.db, self.conversation_id)(self._start_conversation_impl)
        return await decorated_method(call_sid, background_tasks, output_type)

    async def _start_conversation_impl(
        self, call_sid: str, background_tasks: BackgroundTasks, output_type: OutputType = OutputType.TEXT
    ) -> list[str]:
        """Implementation of start_conversation with error handling applied."""
        self.start_flow("intro_flow")

        if self.initial_message_generated:
            while self.initial_message_object is None:
                await asleep(0.1)
            logger.info("Using pre-generated initial utterance")
            initial_message_object = self.initial_message_object
        else:
            logger.info("Generating initial utterance on demand")
            initial_message_object = await self._get_next_utterance(
                context=UnderstandingContext(),
                user_message="",
                output_type=output_type,
                background_tasks=background_tasks,
            )

        intro_message, core_message, initial_message, initial_message_string = self._get_intro_and_core_messages(
            initial_message_object
        )

        logger.info(f"Initial message for the user: {initial_message_string}")
        self.memory.update_conversation(self.conversation_id, call_sid)

        self.conversation_state.add_to_history(
            core_message,
            "bot",
            initial_message_object.intent_name,
            initial_message_object.utterance_name,
            intro_message,
        )
        await self.memory.store_bot_message(self.conversation_id, initial_message_string)
        self._update_context_in_db()

        if output_type == OutputType.URL:
            return [url[1] for url in initial_message_object.urls]

        return initial_message

    def set_first_message_sent_time(self) -> None:
        """Set the time when the first message was sent."""
        self.first_message_sent_time = datetime.now()

    def _get_last_user_message(self) -> str:
        """Get the last message from the user in the conversation history."""
        for message in reversed(self.conversation_state.conversation_history):
            if message.role == "user":
                return message.content
        return ""

    async def handle_empty_transcription(self, output_type: OutputType = OutputType.TEXT) -> list[str]:
        """Handle empty or missing transcription by generating a prompt to continue conversation."""
        logger.info(f"Handling empty transcription - count: {self.no_transcription_count}")

        # During booking_flow, say a reminder on the first timeout in a sequence
        current_flow = self.flow_stack.current_flow
        last_user_message = self._get_last_user_message()
        if (
            current_flow
            and isinstance(current_flow, BookingFlow)
            and self.no_transcription_count == 1
            and settings.booking_flow.contains_trigger_word(last_user_message)
        ):
            prompt_text = "I’m still here and available whenever you’re ready to continue."

            await self.memory.store_user_message(self.conversation_id, "", 0.0)
            await self.memory.store_bot_message(self.conversation_id, prompt_text)
            self._update_context_in_db()

            if output_type == OutputType.URL:
                return [await self.tts_service.generate_recording(prompt_text)]
            return [prompt_text]

        # If we've had too many consecutive empty transcriptions, end the call
        if self.no_transcription_count >= 3:
            logger.info("Too many consecutive empty transcriptions, ending call")
            self.is_running = False
            goodbye_text = "I haven't been able to hear you clearly. I'll end this call now. Goodbye!"

            if output_type == OutputType.URL:
                return [await self.tts_service.generate_recording(goodbye_text)]
            return [goodbye_text]

        # Otherwise, provide a helpful prompt to continue
        if self.no_transcription_count == 1:
            prompt_text = "I didn't catch that. Could you please speak a bit louder or repeat what you said?"
        else:
            prompt_text = "I'm still having trouble hearing you clearly. Please try speaking directly into your phone."

        await self.memory.store_user_message(self.conversation_id, "", 0.0)
        await self.memory.store_bot_message(self.conversation_id, prompt_text)

        if output_type == OutputType.URL:
            return [await self.tts_service.generate_recording(prompt_text)]
        return [prompt_text]

    @profile_method()
    async def handle_single_message(
        self,
        user_message: str,
        background_tasks: BackgroundTasks,
        confidence: float = 1.0,
        output_type: OutputType = OutputType.TEXT,
        skip_understanding: bool = False,
    ) -> list[str]:
        """Handle a single message from the user and return the response message."""
        decorated_method = handle_errors(self.memory.db, self.conversation_id)(self._handle_single_message_impl)
        return await decorated_method(user_message, background_tasks, confidence, output_type, skip_understanding)

    async def _handle_single_message_impl(
        self,
        user_message: str,
        background_tasks: BackgroundTasks,
        confidence: float = 1.0,
        output_type: OutputType = OutputType.TEXT,
        skip_understanding: bool = False,
    ) -> list[str]:
        """Implementation of handle_single_message with error handling applied."""
        logger.info(f"Flows in the stack: {[flow.name for flow in self.flow_stack.flows]}")
        logger.info(f"Transcription {user_message} with confidence: {confidence}")
        self.turn_count += 1

        # Handle low-confidence transcriptions; sometimes confidence is returned as 0 and should be ignored
        if user_message == "" or (
            confidence > 0 and confidence < self.config.TRANSCRIPTION_CONFIDENCE_THRESHOLD and not skip_understanding
        ):
            return await self._handle_low_confidence_transcription(
                confidence, user_message, output_type, background_tasks
            )

        voicemail_detection_result = None
        if self.turn_count == 1:
            voicemail_detector = VoicemailDetector()
            voicemail_detection_result = await voicemail_detector.detect_voicemail(user_message)

        self.conversation_state.add_to_history(user_message, "user")

        current_flow = self.flow_stack.current_flow
        active_slot = current_flow.get_active_slot_name() if current_flow else None
        context = UnderstandingContext(
            current_flow=current_flow,
            conversation_history=self.conversation_state.get_conversation_history(),
        )

        if current_flow:
            current_flow = self._handle_current_flow(user_message, context, output_type, skip_understanding)

        if voicemail_detection_result and voicemail_detection_result.is_voicemail:
            response = await self._handle_voicemail(user_message)
            self._update_context_in_db()
            await self._store_status(current_flow, user_message, confidence)
            return [response]

        if self.transfer_to_human:
            self.is_running = False
            await self._store_status(current_flow, user_message, confidence)
            return [await self._get_human_handoff_message(output_type)]

        if current_flow and current_flow.is_flow_complete():
            self._handle_flow_completion(current_flow)

        bot_message_object: ChatbotResponse | None = None
        if self.is_running and self.flow_stack.current_flow:
            bot_message_object = await self._get_next_utterance(
                context=context,
                user_message=user_message,
                output_type=output_type,
                background_tasks=background_tasks,
                active_slot=active_slot,
            )
            await self._store_status(current_flow, user_message, confidence)

            if "TRANSFER_TO_HUMAN" in bot_message_object.texts[0][1]:
                self.transfer_to_human = True
                self.is_running = False
                return [await self._get_human_handoff_message(output_type)]

            if bot_message_object.intent_name == "resignation_goodbye":
                self.is_running = False

            if bot_message_object.intent_name == "booking_goodbye":
                self.is_running = False

        if not bot_message_object:
            self._update_context_in_db()
            final_text = "Thank you for your time and goodbye."
            if output_type == OutputType.URL:
                url = await self.tts_service.generate_recording(final_text)
                return [url]
            return [final_text]

        intro_message, core_message, bot_message, bot_message_string = self._get_intro_and_core_messages(
            bot_message_object
        )

        self.conversation_state.add_to_history(
            core_message,
            "bot",
            bot_message_object.intent_name,
            bot_message_object.utterance_name,
            intro_message,
        )
        await self.memory.store_bot_message(self.conversation_id, bot_message_string)
        self._update_context_in_db()

        # Handle different response types
        if output_type == OutputType.URL:
            return [url[1] for url in bot_message_object.urls]
        else:
            return bot_message

    async def _store_status(self, current_flow: Flow | None, user_message: str, confidence: float) -> None:
        status = current_flow.get_conversation_status() if current_flow else ConversationStatus.COMPLETED
        lead_status = current_flow.get_lead_status() if current_flow else LeadStatus.UNKNOWN
        await self.memory.store_user_message(
            self.conversation_id, user_message, status=status, lead_status=lead_status, confidence=confidence
        )

    def _handle_current_flow(
        self,
        user_message: str,
        context: UnderstandingContext,
        output_type: OutputType,
        skip_understanding: bool = False,
    ) -> Flow | None:
        if not skip_understanding:
            action_obj: Action = self.understanding_engine.understand(user_message, context)
            logger.info(f"Detected action: {action_obj.model_dump()}")
            self.run_action(action_obj)

        current_flow = self.flow_stack.current_flow  # re-fetch current flow after action
        if current_flow:
            self._handle_human_transfer(current_flow)

        return current_flow

    def is_first_message_interrupted(self) -> bool:
        """
        Detect if the first message was interrupted by checking timing and turn count.

        Returns True if:
        1. This is the first turn (turn_count == 1)
        2. We're in intro_flow
        3. The user responded very quickly after the first message was sent (likely interruption)
        """
        if self.turn_count > 1:
            return False

        if not self.flow_stack.current_flow or self.flow_stack.current_flow.name != "intro_flow":
            return False

        if not self.first_message_sent_time:
            return False

        # If user responds within FIRST_MESSAGE_INTERRUPTION_SECONDS seconds of the first message being sent,
        # consider it an interruption
        time_since_first_message = (datetime.now() - self.first_message_sent_time).total_seconds()
        logger.info(f"Time since first message sent: {time_since_first_message:.2f}s")
        is_quick_response = time_since_first_message <= self.config.FIRST_MESSAGE_INTERRUPTION_SECONDS

        if is_quick_response:
            logger.info(f"Quick response detected: {time_since_first_message:.2f}s after first message sent")

        return is_quick_response

    def _handle_human_transfer(self, current_flow: Flow) -> None:
        self.transfer_to_human = current_flow.get_global_slots()["transfer_to_human"].value  # type: ignore

        # Also check user_wants_human_transfer slot from resignation flow
        if current_flow.name == "resignation_flow":
            user_wants_transfer = current_flow.slots.get("user_wants_human_transfer")
            if user_wants_transfer and user_wants_transfer.value is True:
                self.transfer_to_human = True

    def _is_booking_made_in_booking_flow(self) -> bool:
        """Check if a booking is completed in any booking flow on the stack."""
        return any(isinstance(flow, BookingFlow) and flow.booking_made for flow in self.flow_stack.flows)

    @staticmethod
    def _get_intro_and_core_messages(bot_message_object: ChatbotResponse) -> tuple[str, str, list[str], str]:
        bot_message = [text[1] for text in bot_message_object.texts]
        core_message = " ".join([text[1] for text in bot_message_object.texts if text[0] == "core"])
        intro_message = " ".join([text[1] for text in bot_message_object.texts if text[0] == "intro"])
        bot_message_string = intro_message + " " + core_message
        return intro_message, core_message, bot_message, bot_message_string

    def _handle_flow_completion(self, current_flow: Flow) -> None:
        """Handle the completion of a flow, including cleanup and potential flow transitions."""
        flow_name = current_flow.name
        self.flow_stack.pop()
        logger.info(f"Flow '{flow_name}' completed and removed from stack.")

        if isinstance(current_flow, IntroFlow):
            next_flow = current_flow.get_next_flow()
            self.start_flow(next_flow)
            logger.info(f"Automatically started {next_flow} after intro_flow completion.")

        if self.flow_stack.is_empty():
            self.is_running = False
            logger.info("Flow stack is empty. Stopping conversation.")

    async def _handle_voicemail(self, user_message: str) -> str:
        """Handles the case when a voicemail is detected in the first message."""
        logger.info("Detected voicemail in the first message.")

        await self.memory.store_user_message(
            self.conversation_id,
            user_message,
            confidence=1.0,
            status=ConversationStatus.VOICEMAIL,
            lead_status=LeadStatus.UNKNOWN,
        )
        self.is_running = False

        return ""

    def run_action(self, action: Action) -> None:
        """Runs an action by dispatching to the appropriate method based on action type."""
        current_flow = self.flow_stack.current_flow
        current_flow_name = current_flow.name if current_flow else "None"

        try:
            current_flow = self.flow_stack.current_flow
            if (
                current_flow
                and current_flow.name == "booking_flow"
                and not self._is_booking_flow_action_allowed(action)
            ):
                return

            if isinstance(action.action, SetSlotAction):
                self.set_slot(action.action.flow_name, action.action.slot_name, action.action.slot_value)
            elif isinstance(action.action, StartFlowAction):
                if action.action.flow_name == current_flow_name:
                    logger.warning("Attempted to start a flow while already in it. Ignoring action.")
                else:
                    self.start_flow(action.action.flow_name)
            elif isinstance(action.action, ContinueAction):
                logger.info("Continuing the current flow without changing slots.")
            elif isinstance(action.action, RepetitionAction) and not self.is_first_message_interrupted():
                self.repetition(action.action.user_message)
            else:
                logger.warning(f"Unknown action type: {type(action.action)}")
        except Exception as e:
            logger.error(f"Error executing action {action.action.action_type}: {e}")

    def set_slot(self, flow_name: str, slot_name: str, slot_value: Any) -> None:
        """Sets a slot value for any flow on the flow stack, handling both global and local slots."""
        global_slots = Flow.get_global_slots()
        logger.info(f"Current global slots: {[(name, slot.value) for name, slot in global_slots.items()]}")

        if flow_name == "global":
            if slot_name in global_slots:
                global_slots[slot_name].value = slot_value
                logger.info(f"Set global slot '{slot_name}' to '{slot_value}'")
            else:
                logger.warning(f"Global slot '{slot_name}' not found.")
        else:
            target_flow = next((flow for flow in self.flow_stack.flows if flow.name == flow_name), None)
            if target_flow:
                local_slots = target_flow.local_slots
                logger.info(
                    f"Current local slots for flow '{flow_name}': "
                    f"{[(name, slot.value) for name, slot in local_slots.items()]}"
                )
                if slot_name in local_slots:
                    target_flow.local_slots[slot_name].value = slot_value
                    logger.info(f"Set local slot '{slot_name}' in flow '{flow_name}' to '{slot_value}'")
                else:
                    logger.warning(f"Local slot '{slot_name}' not found in flow '{flow_name}'.")
            else:
                logger.warning(f"Flow '{flow_name}' not found on flow stack. Cannot set slot.")

        current_flow = self.flow_stack.current_flow
        if current_flow:
            active_slots = current_flow.get_active_slots()
            logger.info(f"Current flow '{current_flow.name}' active slots: {[slot.name for slot in active_slots]}")

    def cancel_flow(self) -> None:
        """Action to cancel the current flow."""
        if not self.flow_stack.is_empty():
            current_flow = self.flow_stack.current_flow
            flow_name = current_flow.name if current_flow else "Unknown"
            self.flow_stack.pop()
            logger.info(f"Cancelled and removed flow '{flow_name}' from stack.")
            if self.flow_stack.is_empty():
                self.is_running = False
                logger.info("Flow stack is empty. Stopping conversation.")
        else:
            logger.warning("Attempted to cancel flow, but flow stack is already empty.")

    def start_flow(self, flow_name: str) -> None:
        """Start a new flow with a fresh instance."""
        flow_class = type(FLOW_REGISTRY[flow_name])
        fresh_flow = flow_class()

        self.flow_stack.push(fresh_flow)
        self.is_running = True
        logger.info(f"Started fresh flow instance: {flow_name}")
        logger.debug(f"Flow instance ID: {id(fresh_flow)}")

        self.inject_flow_with_data(fresh_flow)

    def repetition(self, user_message: str) -> None:
        """Start repetition flow when the last user response was not understood."""
        self.start_flow("repetition_flow")

    def rebuttal(self, user_message: str) -> None:
        """Start rebuttal flow when the user raises an objection."""
        self.start_flow("rebuttal_flow")

    def inject_flow_with_data(self, flow: Flow) -> None:
        """Inject necessary data into a flow instance based on its type."""
        # Set bot_name for all flows that support it
        flow.set_bot_name(self.bot_name)
        if self.bot_name:
            logger.info(f"Set bot_name to '{self.bot_name}' for flow: {type(flow).__name__}")

        flow.user_name = self.conversation_state.lead_info.get("user_name")
        logger.info(f"Set user_name to '{flow.user_name}' for flow: {type(flow).__name__}")

        if isinstance(flow, IntroFlow):
            flow.funeral_home_name = self.conversation_state.lead_info.get("funeral_home_name")
            flow.intro_message_version = self.intro_message_version
            logger.info(
                f"Injected lead data into IntroFlow - Funeral home: {flow.funeral_home_name}, "
                f"Intro version: {flow.intro_message_version}"
            )
        elif isinstance(flow, BookingFlow):
            flow.initial_date = self.conversation_state.initial_date
            flow.available_dates = self.conversation_state.available_dates
            logger.info(
                f"Injected calendar data into BookingFlow - Initial date: {self.conversation_state.initial_date}"
            )
        elif isinstance(flow, QuestionFlow):
            flow.funeral_home_address = self.conversation_state.lead_info.get("funeral_home_address")
            logger.info(f"Injected funeral home address into QuestionFlow - Address: {flow.funeral_home_address}")

    async def _get_human_handoff_message(self, output_type: OutputType) -> str:
        if output_type == OutputType.URL:
            await asleep(1.5)
            return self.tts_service.get_recording_url("human_handoff", "example_chatbot_response_1")
        else:
            # Create a temporary flow to access the CSV data
            temp_flow = ResignationFlow()
            return temp_flow._get_utterance("human_handoff").utterance_content

    async def _get_next_utterance(
        self,
        context: UnderstandingContext,
        output_type: OutputType,
        background_tasks: BackgroundTasks,
        user_message: str = "",
        active_slot: str | None = None,
    ) -> ChatbotResponse:
        """Get the next utterance from the current flow based on slot state."""
        current_flow = self.flow_stack.current_flow
        if not current_flow:
            text = "Thank you for your time and goodbye."
            url = await self.tts_service.generate_recording(text) if output_type == OutputType.URL else ""
            return ChatbotResponse(
                response_type=ChatbotResponseType.DYNAMIC, texts=[("core", text)], urls=[("core", url)]
            )

        logger.info(f"Getting next utterance for flow: {current_flow.name}")

        if isinstance(current_flow, QuestionFlow):
            return await self._handle_question_flow(
                current_flow, context, user_message, output_type, background_tasks, active_slot
            )
        elif isinstance(current_flow, RepetitionFlow):
            return await self._handle_repetition_flow(
                current_flow, context, user_message, output_type, background_tasks
            )

        response = await current_flow.get_next_utterance(
            context=context,
            user_message=user_message,
            background_tasks=background_tasks,
            lead_data=self.conversation_state.lead_info,
            conversation_id=self.conversation_id,
        )
        utterance_response = response.utterance_content
        intro_response = response.intro_content

        logger.info(f"Chatbot response: {intro_response} {utterance_response}")

        if isinstance(current_flow, IntroFlow) and utterance_response == "REBUTTAL_ANSWER":
            self.rebuttal(user_message)
            rebuttal_flow = cast(RebuttalFlow, self.flow_stack.current_flow)
            return await self._handle_rebuttal_flow(rebuttal_flow, context, user_message, output_type, background_tasks)

        is_static_response = self._is_static_response(current_flow, response.intent_name)

        if is_static_response:
            if output_type == OutputType.URL:
                intent_name = response.intent_name
                utterance_name = response.utterance_name
                response_url = self.tts_service.get_recording_url(intent_name, utterance_name)
                intro_url = (
                    self.tts_service.get_recording_url(intent_name, "intro_chatbot_response") if intro_response else ""
                )
            else:
                response_url = ""
                intro_url = ""
            texts = (
                [("intro", intro_response), ("core", utterance_response)]
                if intro_response
                else [("core", utterance_response)]
            )
            urls = [("intro", intro_url), ("core", response_url)] if intro_response else [("core", response_url)]
            return ChatbotResponse(
                response_type=ChatbotResponseType.STATIC,
                texts=texts,
                urls=urls,
                intent_name=response.intent_name,
                utterance_name=response.utterance_name,
            )
        else:
            response_url = (
                await self.tts_service.generate_recording(utterance_response) if output_type == OutputType.URL else ""
            )
            intro_url = (
                await self.tts_service.generate_recording(intro_response)
                if output_type == OutputType.URL and intro_response
                else ""
            )
            texts = (
                [("intro", intro_response), ("core", utterance_response)]
                if intro_response
                else [("core", utterance_response)]
            )
            urls = [("intro", intro_url), ("core", response_url)] if intro_response else [("core", response_url)]
            return ChatbotResponse(
                response_type=ChatbotResponseType.DYNAMIC,
                texts=texts,
                urls=urls,
                intent_name=response.intent_name,
                utterance_name=response.utterance_name,
            )

    @staticmethod
    def _is_static_response(current_flow: Flow, slot_name: str) -> bool:
        """Determine if the response is static or dynamic."""
        # TODO: Add loading info about static vs dynamic response from CSV file
        return not isinstance(current_flow, BookingFlow) and slot_name not in [
            "confirm_identity",
            "what_is_your_address_or_location",
            "booking_flow",
        ]

    async def _handle_question_flow(
        self,
        current_flow: QuestionFlow,
        context: UnderstandingContext,
        user_message: str,
        output_type: OutputType,
        background_tasks: BackgroundTasks,
        active_slot: str | None = None,
    ) -> ChatbotResponse:
        """Handle QuestionFlow specific logic and return the appropriate utterance."""
        question_response = self.understanding_engine.understand_question(user_message)
        current_flow.chatbot_response = question_response

        need_pause = active_slot in {"accept_appointment", "offer_rebuttal"}
        question_response = await current_flow.get_next_utterance(
            context=context, user_message=user_message, background_tasks=background_tasks, need_pause=need_pause
        )
        self._handle_flow_completion(current_flow)

        if "TRANSFER_TO_HUMAN" in question_response.utterance_content:
            self.transfer_to_human = True
            self.is_running = False
            return ChatbotResponse(
                response_type=ChatbotResponseType.STATIC,
                texts=[("core", question_response.utterance_content)],
                urls=[],
            )

        if question_response.intent_name == "do_not_call_me_again":
            self.is_running = False
            response_url = self.tts_service.get_recording_url(
                question_response.intent_name, question_response.utterance_name
            )
            return ChatbotResponse(
                response_type=ChatbotResponseType.STATIC,
                texts=[("core", question_response.utterance_content)],
                urls=[("core", response_url)],
            )

        if self._is_booking_made_in_booking_flow():
            logger.info("Booking made in booking flow - changing previous bot response content to generic question")
            previous_bot_utterance = context.previous_bot_utterance.model_copy(
                update={"content": "What else can I assist you with today?"}
            )
        else:
            previous_bot_utterance = context.previous_bot_utterance

        return await self._rephrase_previous_bot_response(
            question_response,
            previous_bot_utterance,
            current_flow,
            output_type,
        )

    async def _handle_repetition_flow(
        self,
        current_flow: RepetitionFlow,
        context: UnderstandingContext,
        user_message: str,
        output_type: OutputType,
        background_tasks: BackgroundTasks,
    ) -> ChatbotResponse:
        """Handle RepetitionFlow specific logic and return the appropriate utterance."""
        repetition_response = await current_flow.get_next_utterance(
            context=context, user_message=user_message, background_tasks=background_tasks
        )
        self._handle_flow_completion(current_flow)

        return await self._rephrase_previous_bot_response(
            repetition_response,
            context.previous_bot_utterance,
            current_flow,
            output_type,
        )

    async def _handle_rebuttal_flow(
        self,
        current_flow: RebuttalFlow,
        context: UnderstandingContext,
        user_message: str,
        output_type: OutputType,
        background_tasks: BackgroundTasks,
    ) -> ChatbotResponse:
        """Handle RebuttalFlow specific logic and return the appropriate utterance."""
        rebuttal_response = self.understanding_engine.understand_objection(user_message)
        logger.info(f"Chatbot response for objection: {rebuttal_response.utterance_content}")
        current_flow.chatbot_response = rebuttal_response
        rebuttal_response = await current_flow.get_next_utterance(
            context=context, user_message=user_message, background_tasks=background_tasks
        )
        self._handle_flow_completion(current_flow)

        return await self._rephrase_previous_bot_response(
            rebuttal_response,
            context.previous_bot_utterance,
            current_flow,
            output_type,
        )

    async def _handle_low_confidence_transcription(
        self, confidence: float, user_message: str, output_type: OutputType, background_tasks: BackgroundTasks
    ) -> list[str]:
        logger.info(f"Low transcription confidence: {confidence} < {self.config.TRANSCRIPTION_CONFIDENCE_THRESHOLD}")

        self.conversation_state.add_to_history(user_message, "user")
        self.start_flow("repetition_flow")

        repetition_flow = cast(RepetitionFlow, self.flow_stack.current_flow)
        context = UnderstandingContext(
            current_flow=repetition_flow,
            conversation_history=self.conversation_state.get_conversation_history(),
        )

        bot_message_object = await self._handle_repetition_flow(
            repetition_flow, context, user_message, output_type, background_tasks
        )

        intro_message, core_message, bot_message, bot_message_string = self._get_intro_and_core_messages(
            bot_message_object
        )

        self.conversation_state.add_to_history(
            core_message,
            "bot",
            bot_message_object.intent_name,
            bot_message_object.utterance_name,
            intro_message,
        )

        await self.memory.store_user_message(
            self.conversation_id,
            user_message,
            confidence,
            status=ConversationStatus.ANSWERED,
            lead_status=LeadStatus.UNKNOWN,
        )
        await self.memory.store_bot_message(self.conversation_id, bot_message_string)
        self._update_context_in_db()

        if output_type == OutputType.URL:
            return [url[1] for url in bot_message_object.urls]
        else:
            return bot_message

    async def _rephrase_previous_bot_response(
        self,
        new_intro_response: Response,
        previous_bot_message: Message,
        current_flow: Flow,
        output_type: OutputType,
    ) -> ChatbotResponse:
        # For repeating previous bot utterance we want to sample a different core part
        # of the previous bot utterance without the intro part
        # and include a new intro part instead (question response or repetition request)
        if previous_bot_message.intent_name == "confirm_identity":
            if current_flow.user_name:
                replacements = {"USER_NAME": current_flow.user_name}
                rephrased_previous_bot_utterance = current_flow._get_utterance(
                    slot_name="confirm_identity", replacements=replacements, include_intro=False
                )
            else:  # Fallback if for some reason user_name is not set in a given flow
                logger.warning("The user_name field is not set in current flow, doing full rephrasing")
                rephrased_previous_bot_utterance = self.rephraser.rephrase(
                    new_intro_response.utterance_content, previous_bot_message.content.split(".")[-1]
                )
        elif not self._is_static_response(current_flow, previous_bot_message.intent_name):
            rephrased_previous_bot_utterance = self.rephraser.rephrase(
                new_intro_response.utterance_content, previous_bot_message.content
            )
        else:
            rephrased_previous_bot_utterance = current_flow._get_utterance(
                previous_bot_message.intent_name, include_intro=False
            )

        rephrased_previous_bot_message = Message(
            content=rephrased_previous_bot_utterance.utterance_content,
            role="bot",
            intent_name=previous_bot_message.intent_name,
            utterance_name=rephrased_previous_bot_utterance.utterance_name,
        )

        texts = [
            ("intro", new_intro_response.utterance_content),
            ("core", rephrased_previous_bot_message.content),
        ]

        if output_type == OutputType.URL:
            if not self._is_static_response(current_flow, new_intro_response.intent_name):
                new_intro_utterance_url: str = await self.tts_service.generate_recording(
                    new_intro_response.utterance_content
                )
            else:
                new_intro_utterance_url = self.tts_service.get_recording_url(
                    new_intro_response.intent_name, new_intro_response.utterance_name
                )
            if self._is_static_response(current_flow, rephrased_previous_bot_message.intent_name):
                previous_bot_utterance_url = self.tts_service.get_recording_url(
                    rephrased_previous_bot_message.intent_name, rephrased_previous_bot_message.utterance_name
                )
            else:
                previous_bot_utterance_url = await self.tts_service.generate_recording(
                    rephrased_previous_bot_message.content
                )
            urls = [
                ("intro", new_intro_utterance_url),
                ("core", previous_bot_utterance_url),
            ]
        else:
            urls = []
        # Response type doesn't matter here because we already have recordings generated
        chatbot_response = ChatbotResponse(
            response_type=ChatbotResponseType.STATIC,
            texts=texts,
            urls=urls,
            intent_name=previous_bot_message.intent_name,
        )
        return chatbot_response

    @staticmethod
    def _is_booking_flow_action_allowed(action: Action) -> bool:
        """Check if an action is allowed during booking flow."""
        if isinstance(action.action, StartFlowAction):
            if action.action.flow_name == "question_flow":
                return True
            else:
                logger.warning(f"Action ignored: Cannot start flow '{action.action.flow_name}' during booking flow.")
                return False

        if isinstance(action.action, SetSlotAction):
            if action.action.flow_name == "global":
                return True
            else:
                logger.warning(
                    f"Action ignored: Cannot set slot '{action.action.slot_name}' "
                    f"in flow '{action.action.flow_name}' during booking flow."
                )
                return False

        return True
