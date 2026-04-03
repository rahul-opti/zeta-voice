import re
from abc import ABC, abstractmethod
from asyncio import sleep
from datetime import date, datetime
from re import Match
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import pandas as pd
from fastapi import BackgroundTasks
from jinja2 import Environment, FileSystemLoader
from litellm import completion
from loguru import logger
from num2words import num2words
from pandas import DataFrame

from zeta_voice.conversation import calendar_api
from zeta_voice.conversation.calendar_api import mock_send_to_booking_api
from zeta_voice.conversation.models import BookingFlowMessage, Slot
from zeta_voice.paths import (
    BOOKING_FLOW_PROMPT_PATH,
    INTRO_MESSAGES_PATH,
    REPETITION_UTTERANCES_PATH,
    SLOTS_WITH_RESPONSES_PATH,
)
from zeta_voice.settings import BookingFlowSettings, settings
from zeta_voice.utils.enums import ConversationStatus, LeadStatus
from zeta_voice.utils.helpers import (
    Response,
    Utterance,
    filter_and_sample_responses,
    load_json,
    load_utterances_config,
)

if TYPE_CHECKING:
    from zeta_voice.conversation.context import UnderstandingContext


class Flow(ABC):
    """Base class for all conversation flows."""

    _global_slots: dict[str, Slot] = {}

    def __init__(self) -> None:
        self.name: str
        self.description: str
        self.flows_config: DataFrame = load_utterances_config(str(SLOTS_WITH_RESPONSES_PATH))
        self.local_slots: dict[str, Slot] = self._init_local_slots()
        self.awaits_user_input: bool = True

        self.bot_name: str
        self.user_name: str | None = None

    @classmethod
    def get_global_slots(cls) -> dict[str, Slot]:
        """Get global slots shared across all flows."""
        if not cls._global_slots:
            cls.init_global_slots()
        return cls._global_slots

    @classmethod
    def init_global_slots(cls) -> dict[str, Slot]:
        """Initialize global slots that are shared across all flows."""
        slots = [
            Slot(
                name="transfer_to_human",
                description=(
                    """
                    Whether user explicitly requests to speak with a human operator or live agent.
                    Set to True ONLY when user directly asks to talk to a person, human, agent,
                    representative, or uses phrases like 'let me speak to someone', 'transfer me', or
                    'I want to talk to a real person'.
                    DO NOT set to True for identity questions like 'Are you a real person?', 'Are you a bot?', '
                    'You don't sound human', or similar questions about the AI's nature'
                    Never set to False - only set to True when explicitly requesting transfer to human.
                    """
                ),
                value=False,
                type="bool",
            ),
        ]
        cls._global_slots = {s.name: s for s in slots}
        return cls._global_slots

    @classmethod
    def update_global_slots(cls, data: dict[str, Any]) -> None:
        """Update global slots with data where keys match slot names."""
        global_slots = cls.get_global_slots()
        for key, value in data.items():
            if key in global_slots:
                global_slots[key].value = value

    def set_bot_name(self, bot_name: str) -> None:
        """Set the bot name for this flow instance."""
        self.bot_name = bot_name

    @property
    def slots(self) -> dict[str, Slot]:
        """Get all slots (global + local) for the flow."""
        all_slots = {}
        all_slots.update(self.get_global_slots())
        all_slots.update(self.local_slots)
        return all_slots

    def get_active_slots(self) -> list[Slot]:
        """Get all local slots that have None value and meet required_slots conditions."""
        if self.name == "booking_flow":
            return []

        return [slot for slot in self.local_slots.values() if self.is_slot_active(slot)]

    def get_active_slot(self) -> Slot:
        """Get the first active local slot that has None value and meets required_slots conditions."""
        active_slots = self.get_active_slots()
        return active_slots[0]

    def get_active_slot_name(self) -> str | None:
        """Get the name of the first active local slot that has None value and meets required_slots conditions."""
        active_slots = self.get_active_slots()
        return active_slots[0].name if active_slots else None

    def is_slot_active(self, slot: Slot) -> bool:
        """Check if a slot is active based on its value and required_slots conditions.
        Slot is active if at least one required_slot_name has expected_value (OR logic)
        """
        if slot.value is not None:
            return False

        if not slot.required_slots:
            return True

        for required_slot_name, expected_value in slot.required_slots:
            if required_slot_name not in self.slots:
                continue
            if self.slots[required_slot_name].value == expected_value:
                return True

        return False

    def _get_utterance(
        self, slot_name: str, replacements: dict[str, str] | None = None, include_intro: bool = True
    ) -> Utterance:
        """Get a random utterance for the given slot from the CSV configuration."""
        if slot_name not in self.flows_config.index:
            return Utterance(
                utterance_name="utterance_not_found", utterance_content=f"Utterance not found for slot: {slot_name}"
            )

        row = self.flows_config.loc[slot_name]
        utterance = filter_and_sample_responses(row, include_intro=include_intro)

        if replacements:
            for placeholder, value in replacements.items():
                if value:
                    utterance.utterance_content = utterance.utterance_content.replace(placeholder, value)
                    utterance.intro_content = utterance.intro_content.replace(placeholder, value)

        return utterance

    def _init_local_slots(self) -> dict[str, Slot]:
        """Get the local slots specific to this flow loaded from flows_config."""
        flow_slots = self.flows_config[self.flows_config["flow_name"] == self.name]

        slots = []
        for slot_name, row in flow_slots.iterrows():
            slot = Slot(
                name=slot_name,
                description=row["description"],
                value=None,
                type="bool",
                required_slots=row["required_slots"],
            )
            slots.append(slot)

        return {s.name: s for s in slots}

    @abstractmethod
    async def get_next_utterance(
        self,
        context: "UnderstandingContext",
        user_message: str,
        background_tasks: BackgroundTasks,
        lead_data: dict | None = None,
        conversation_id: UUID | None = None,
    ) -> Response:
        """Get the next utterance based on current slot state."""
        pass

    @abstractmethod
    def is_flow_complete(self) -> bool:
        """Check if the flow is complete based on slot state."""
        pass

    @abstractmethod
    def get_conversation_status(self) -> ConversationStatus | None:
        """Get the conversation status based on current flow and slot states."""
        pass

    def get_lead_status(self) -> LeadStatus | None:
        """Get the lead status based on current flow and slot states."""
        human_handoff = bool(self.get_global_slots()["transfer_to_human"].value)

        if human_handoff:
            return LeadStatus.TRANSFERRED

        return None


class IntroFlow(Flow):
    """Flow for introducing the conversation, confirming identity, and presenting sales pitch."""

    def __init__(self) -> None:
        self.name = "intro_flow"
        self.description = (
            "Introduces the conversation with a lead, confirms identity, presents sales pitch and offers appointments"
        )
        self.funeral_home_name: str | None = None
        self.intro_message_version: str | None = None
        super().__init__()

    async def get_next_utterance(
        self,
        context: "UnderstandingContext",
        user_message: str,
        background_tasks: BackgroundTasks,
        lead_data: dict | None = None,
        conversation_id: UUID | None = None,
    ) -> Response:
        """Determine the next utterance based on active slot and current state."""
        active_slot = self.get_active_slot()
        replacements = self._get_replacements()
        utterance = self._get_utterance(active_slot.name, replacements)
        response = Response(
            intent_name=active_slot.name,
            utterance_name=utterance.utterance_name,
            utterance_content=utterance.utterance_content,
            intro_content=utterance.intro_content,
        )
        return response

    def _get_replacements(self) -> dict[str, str]:
        """Get replacements for placeholders in utterances."""
        replacements = {}
        if self.funeral_home_name:
            replacements["FUNERAL_HOME_NAME"] = self.funeral_home_name
        if self.user_name:
            replacements["USER_NAME"] = self.user_name
        if self.bot_name:
            replacements["BOT_NAME"] = self.bot_name

        return replacements

    def _get_utterance(
        self,
        slot_name: str,
        replacements: dict[str, str] | None = None,
        include_intro: bool = False,
    ) -> Utterance:
        """Get a random utterance for the given slot, with custom intro message support for confirm_identity."""
        # For confirm_identity slot, use custom intro message if available
        if slot_name == "confirm_identity" and self.intro_message_version:
            try:
                intro_messages_config = load_json(str(INTRO_MESSAGES_PATH))
                versions = intro_messages_config.get("versions", {})

                if self.intro_message_version in versions:
                    custom_intro = versions[self.intro_message_version]["message"]

                    if replacements:
                        for placeholder, value in replacements.items():
                            if value:
                                custom_intro = custom_intro.replace(placeholder, value)

                    return Utterance(utterance_name="custom_intro", utterance_content=custom_intro, intro_content="")
            except Exception as e:
                logger.warning(f"Failed to load custom intro message, falling back to default: {e}")

        # Default behavior for all other slots
        return super()._get_utterance(slot_name, replacements)

    def is_flow_complete(self) -> bool:
        """Check if the flow is complete based on slot state."""
        accept_appointment = self.slots["accept_appointment"].value
        offer_rebuttal = self.slots["offer_rebuttal"].value
        accept_preplanning = self.slots["accept_preplanning"].value
        confirm_identity = self.slots["confirm_identity"].value

        return (
            bool(accept_appointment)
            or offer_rebuttal is not None
            or (accept_preplanning is True and confirm_identity is False)
        )

    def get_next_flow(self) -> str:
        """Get the next flow based on the completion state of intro_flow."""
        if self.is_flow_complete():
            accept_appointment = self.slots["accept_appointment"].value
            offer_rebuttal = self.slots["offer_rebuttal"].value
            accept_preplanning = self.slots["accept_preplanning"].value
            confirm_identity = self.slots["confirm_identity"].value

            if (
                accept_appointment is True
                or offer_rebuttal is True
                or (accept_preplanning is True and confirm_identity is False)
            ):
                return "booking_flow"
            else:
                return "resignation_flow"
        else:
            raise ValueError("Flow is not complete, cannot determine next flow")

    def get_conversation_status(self) -> ConversationStatus:
        """Get the conversation status based on intro flow slot states."""
        confirm_identity = self.slots["confirm_identity"].value
        offer_rebuttal = self.slots["offer_rebuttal"].value

        if offer_rebuttal is True:
            return ConversationStatus.START_BOOKING

        if confirm_identity is False:
            return ConversationStatus.WRONG_IDENTITY

        return ConversationStatus.ANSWERED

    def get_lead_status(self) -> LeadStatus:
        """Get the lead status based on intro flow slot states."""
        lead_status = super().get_lead_status()
        if lead_status is not None:
            return lead_status

        offer_rebuttal = self.slots["offer_rebuttal"].value

        if offer_rebuttal is False:
            return LeadStatus.REJECTED

        return LeadStatus.UNKNOWN


class BookingFlow(Flow):
    """Flow for booking appointments after the intro flow."""

    def __init__(self) -> None:
        self.name = "booking_flow"
        self.description = "Handles appointment booking process including scheduling and securing appointments"
        self.initial_date: datetime | None = None
        self.available_dates: list[datetime] = []
        self.selected_datetime: datetime | None = None
        self.user_said_goodbye: bool = False
        self.settings = BookingFlowSettings()
        self.booking_made = False
        self._prompt_template = Environment(loader=FileSystemLoader(searchpath="/"), autoescape=True).get_template(
            str(BOOKING_FLOW_PROMPT_PATH)
        )
        super().__init__()

    @staticmethod
    def _format_times(dates: list[datetime]) -> list[str]:
        formatted_dates = []
        for date_ in dates:
            # Format date and time and remove leading zeros from time
            formatted = date_.strftime("%A, %B %d at %-I:%M %p")
            # Remove trailing zeros from time
            formatted = formatted.replace(":00 ", " ")
            formatted_dates.append(formatted)
        return formatted_dates

    @staticmethod
    def _verbalize_date(text: str) -> str:
        """
        Converts numeric dates (like 'September 02', 'Aug 1', etc.)
        into their spoken form (like 'September second', 'August first').
        """
        # Match month names followed by a day number
        pattern = re.compile(
            r"\b("
            r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
            r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
            r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
            r")\s+(\d{1,2})(\b)",
            flags=re.IGNORECASE,
        )

        def replace_match(match: Match[str]) -> str:
            month = match.group(1)
            day = int(match.group(2))
            day_text = num2words(day, to="ordinal")
            return f"{month} {day_text}"

        return pattern.sub(replace_match, text)

    @staticmethod
    def _neutralize_phrases(text: str) -> str:
        """
        Replaces any of the forbidden phrases with "alright" matching the
        capitalization of original phrase.
        """
        forbidden_phrases = [
            "Excellent choice",
            "Fantastic choice",
            "Wonderful choice",
            "Great choice",
            "Excellent",
            "That works perfectly",
            "Perfect",
            "Wonderful",
            "Great",
            "Fantastic",
            "Excellent",
            "Phenomenal",
            "Outstanding",
            "Superb",
            "Brilliant",
            "Marvelous",
            "Terrific",
            "Splendid",
            "Exceptional",
            "Magnificent",
        ]

        # 1. Sort phrases by length (descending).
        # This ensures "Great choice" is matched before "Great".
        forbidden_phrases.sort(key=len, reverse=True)

        # 2. Build a regex pattern: \b(Phrase1|Phrase2|...)\b
        # re.escape is used to handle any potential special characters safely
        pattern = r"\b(" + "|".join(re.escape(p) for p in forbidden_phrases) + r")\b"

        # 3. Define the replacement logic to handle capitalization
        def replace_case_sensitive(match: re.Match[str]) -> str:
            original = match.group(0)

            if original.isupper():
                return "ALRIGHT"
            elif original[0].isupper():
                # Handles "Great", "Great choice", or "Great Choice"
                return "Alright"
            else:
                return "alright"

        # 4. Perform substitution with IGNORECASE flag
        return re.sub(pattern, replace_case_sensitive, text, flags=re.IGNORECASE)

    async def get_next_utterance(
        self,
        context: "UnderstandingContext",
        user_message: str,
        background_tasks: BackgroundTasks,
        lead_data: dict | None = None,
        conversation_id: UUID | None = None,
    ) -> Response:
        """Determine the next utterance."""
        current_date = date.today()
        prompt = self._prompt_template.render(
            user_message=user_message,
            conversation_history=context.conversation_history if context.conversation_history else [],
            available_dates=self._format_times(self.available_dates),
            initial_date=self._format_times([self.initial_date])[0] if self.initial_date is not None else "",
            booking_flow_persona=self.settings.BOOKING_FLOW_PERSONA,
            current_date=current_date,
        )
        logger.info(prompt)
        logger.info("Sending prompt to LLM for booking flow response generation...")
        response = completion(
            model=self.settings.BOOKING_FLOW_MODEL,
            messages=[{"content": prompt, "role": "user"}],
            response_format=BookingFlowMessage,
        )
        message = BookingFlowMessage.model_validate_json(response.choices[0].message.content)
        logger.info(f"BookingFlowMessage: {message}")

        if message.appointment_datetime is not None:
            self.selected_datetime = message.appointment_datetime

        if message.appointment_datetime is not None and not self.booking_made:
            if settings.calendar.DYNAMICS_ERP_BOOKING and lead_data:
                lead_info = {
                    "lead_id": lead_data.get("lead_id"),
                    "user_name": lead_data.get("user_name", "Unknown"),
                    "email": lead_data.get("email"),
                }
                calendar_id = lead_data.get("calendar_id")
                if not calendar_id:
                    logger.error(
                        f"Cannot book appointment, 'calendar_id' is missing from lead_data for lead {lead_info.get('lead_id')}."  # noqa: E501
                    )
                    message.booking_response_message = (
                        "I'm sorry, I'm having trouble accessing the calendar right now. Please try again later."
                    )
                else:
                    try:
                        background_tasks.add_task(
                            calendar_api.book_appointment,
                            message.appointment_datetime,
                            lead_info,
                            calendar_id,
                            True,
                            conversation_id,
                        )
                    except Exception as e:
                        logger.error(f"Background appointment booking failed for lead {lead_info.get('lead_id')}: {e}")
                    self.booking_made = True
            else:
                self.booking_made = True
                mock_send_to_booking_api(message.appointment_datetime)

        if message.user_said_goodbye:
            self.user_said_goodbye = True
            # Handle goodbye message based on booking status
            if self.selected_datetime is None or not self.booking_made:
                # Fallback message if no datetime is available
                goodbye_message = "Thank you for your time and goodbye."
            else:
                goodbye_message = "Thank you for your time. Enjoy the rest of your day. Goodbye."
            response = Response(
                intent_name="booking_goodbye",
                utterance_name="booking_goodbye",
                utterance_content=self._verbalize_date(goodbye_message),
            )
            response.utterance_content = re.sub(r"\bgreat\b", "good", response.utterance_content, flags=re.IGNORECASE)
            return response

        response = Response(
            intent_name="booking_flow",
            utterance_name="booking_response",
            utterance_content=message.booking_response_message,
        )

        # Remove exclamation marks from booking response message
        response.utterance_content = response.utterance_content.replace("!", ".")

        response.utterance_content = self._neutralize_phrases(response.utterance_content)

        # Verbalize date for TTS
        response.utterance_content = self._verbalize_date(response.utterance_content)

        return response

    def is_flow_complete(self) -> bool:
        """Check if the flow is complete based on slot state."""
        return self.user_said_goodbye

    @staticmethod
    def get_conversation_status() -> ConversationStatus:
        """Get the conversation status based on booking flow slot states."""
        return ConversationStatus.START_BOOKING

    def get_lead_status(self) -> LeadStatus:
        """Get the lead status based on booking flow slot states."""
        lead_status = super().get_lead_status()
        if lead_status is not None:
            return lead_status

        if self.booking_made:
            return LeadStatus.BOOKED

        if self.selected_datetime:
            return LeadStatus.DATE_SELECTED

        return LeadStatus.UNKNOWN


class ResignationFlow(Flow):
    """Flow for handling resignation/rejection scenarios when user declines appointment."""

    def __init__(self) -> None:
        self.name = "resignation_flow"
        self.description = (
            "Handles rejection scenarios when user declines appointment,"
            "offers human handoff, asks if user is interested in attending an upcoming seminar"
            "or being added to the seminar marketing list and gracefully ends conversation"
        )
        super().__init__()

    async def get_next_utterance(
        self,
        context: "UnderstandingContext",
        user_message: str,
        background_tasks: BackgroundTasks,
        lead_data: dict | None = None,
        conversation_id: UUID | None = None,
    ) -> Response:
        """Determine the next utterance based on active slot and current state."""
        active_slot = self.get_active_slot()
        utterance = self._get_utterance(active_slot.name, replacements={})
        response = Response(
            intent_name=active_slot.name,
            utterance_name=utterance.utterance_name,
            utterance_content=utterance.utterance_content,
            intro_content=utterance.intro_content,
        )
        if active_slot.name == "user_wants_human_transfer":
            await sleep(2)  # Simulate a brief pause for realism, filler may be interrupted here
        return response

    def is_flow_complete(self) -> bool:
        """Check if the flow is complete based on slot state."""
        goodbye = bool(self.slots["resignation_goodbye"].value)
        human_handoff = bool(self.slots["human_handoff"].value)
        return goodbye or human_handoff

    @staticmethod
    def get_conversation_status() -> ConversationStatus:
        """Get the conversation status based on resignation flow slot states."""
        return ConversationStatus.RESIGNED

    def get_lead_status(self) -> LeadStatus:
        """Get the lead status based on resignation flow slot states."""
        lead_status = super().get_lead_status()
        if lead_status is not None:
            return lead_status

        human_handoff = bool(self.slots["human_handoff"].value)
        attend_seminar = bool(self.slots["attend_seminar"].value)

        if human_handoff:
            return LeadStatus.TRANSFERRED

        if attend_seminar:
            return LeadStatus.ATTEND_SEMINAR

        return LeadStatus.REJECTED


class QuestionFlow(Flow):
    """Flow for handling user questions using FAQ responses."""

    def __init__(self) -> None:
        self.name = "question_flow"
        self.description = (
            "Handles customer inquiries using pre-configured FAQ responses covering funeral services, "
            "pricing, costs and payment plans, cremation and burial options, pre-planning benefits, "
            "veteran services, grief support, service customization, livestreaming capabilities, "
            "bot identity questions (such as 'who are you?'), contact information requests, and do-not-call requests. "
            "(such as 'do not call this number again')"
            "Provides appropriate fallback responses for out-of-scope questions."
        )
        self.question_answered: bool = False
        self.chatbot_response: Response | None = None
        self.funeral_home_address: str | None = None
        super().__init__()
        self.awaits_user_input = False

    async def get_next_utterance(
        self,
        context: "UnderstandingContext",
        user_message: str,
        background_tasks: BackgroundTasks,
        lead_data: dict | None = None,
        conversation_id: UUID | None = None,
        need_pause: bool = False,
    ) -> Response:
        """Get the next utterance.

        Returns:
            The appropriate FAQ response or error message
        """
        if not self.chatbot_response:
            return Response(
                intent_name="question_flow",
                utterance_name="question_not_understood",
                utterance_content="I'm sorry, I didn't understand your question. Could you please rephrase it?",
            )

        self.question_answered = True

        replacements = self._get_replacements()
        if replacements:
            for placeholder, value in replacements.items():
                if value:
                    self.chatbot_response.utterance_content = self.chatbot_response.utterance_content.replace(
                        placeholder, value
                    )
                    self.chatbot_response.intro_content = self.chatbot_response.intro_content.replace(
                        placeholder, value
                    )

        if need_pause:
            await sleep(1.5)  # Simulate a brief pause for realism
        return self.chatbot_response

    @staticmethod
    def normalize_address_for_tts(address: str) -> str:
        """
        Convert leading house numbers in an address into a digit-by-digit
        spoken form for better TTS output.

        Example:
            "2052 Howard Road, Camarillo, California"
            -> "two oh five two Howard Road, Camarillo, California"
        """
        DIGIT_WORDS = {
            "0": "oh",
            "1": "one",
            "2": "two",
            "3": "three",
            "4": "four",
            "5": "five",
            "6": "six",
            "7": "seven",
            "8": "eight",
            "9": "nine",
        }
        
        if not address:
            return address

        address = address.strip()

        # Match leading house number only, e.g. "2052 Howard Road"
        match = re.match(r"^(\d+)(\b.*)$", address)
        if not match:
            return address

        street_number, rest = match.groups()
        spoken_number = " ".join(DIGIT_WORDS.get(ch, ch) for ch in street_number)

        return f"{spoken_number}{rest}"

    def _get_replacements(self) -> dict[str, str]:
        """Get replacements for placeholders in utterances."""
        replacements = {}
        if self.funeral_home_address:
            replacements["ADDRESS"] = self.normalize_address_for_tts(cast(str, self.funeral_home_address))
        return replacements

    def is_flow_complete(self) -> bool:
        """Check if the flow is complete."""
        return self.question_answered

    def get_conversation_status(self) -> ConversationStatus | None:
        """Get the conversation status based on question flow state."""
        if self.chatbot_response and self.chatbot_response.intent_name == "do_not_call_me_again":
            return ConversationStatus.DO_NOT_CALL
        return None

    def get_lead_status(self) -> LeadStatus | None:
        """Get the lead status based on question flow state."""
        lead_status = super().get_lead_status()
        if lead_status is not None:
            return lead_status

        if self.chatbot_response and self.chatbot_response.intent_name == "do_not_call_me_again":
            return LeadStatus.REJECTED
        return None


class RepetitionFlow(Flow):
    """Flow for handling repetition when user input is not understood."""

    def __init__(self) -> None:
        self.name = "repetition_flow"
        self.description = (
            "Handles cases when user input is not understood and requires repetition of the previous bot message."
        )
        self.repetition_handled: bool = False
        self.chatbot_response: Response | None = None
        super().__init__()
        self.awaits_user_input = False
        self.chatbot_utterance: str = pd.read_csv(str(REPETITION_UTTERANCES_PATH)).iloc[0]["example_chatbot_response_1"]

    async def get_next_utterance(
        self,
        context: "UnderstandingContext",
        user_message: str,
        background_tasks: BackgroundTasks,
        lead_data: dict | None = None,
        conversation_id: UUID | None = None,
    ) -> Response:
        """Get the next utterance.

        Returns:
            The repetition response indicating the message was not understood
        """
        self.chatbot_response = Response(
            intent_name="repetition_not_understood",
            utterance_name="example_chatbot_response_1",
            utterance_content=self.chatbot_utterance,
        )

        self.repetition_handled = True

        return self.chatbot_response

    def is_flow_complete(self) -> bool:
        """Check if the flow is complete."""
        return self.repetition_handled

    @staticmethod
    def get_conversation_status() -> ConversationStatus | None:
        """Get the conversation status based on repetition flow state."""
        return None

    @staticmethod
    def get_lead_status() -> LeadStatus | None:
        """Get the lead status based on repetition flow state."""
        return None


class RebuttalFlow(Flow):
    """Flow for handling rebuttals when user raises objections."""

    def __init__(self) -> None:
        self.name = "rebuttal_flow"
        self.description = (
            "Handles customer objections and concerns about funeral pre-planning services, "
            "including discomfort with death topics, beliefs that planning isn't necessary, "
            "financial concerns and affordability issues, feeling overwhelmed by choices, "
            "lack of time, trust issues with unsolicited calls, perception of morbidity, "
            "existing arrangements or life insurance, age-related concerns, family consultation needs, "
            "pricing inquiries and not being sure if they want to schedule a meeting."
            "Provides empathetic, supportive rebuttal responses to address "
            "specific objections and guide customers toward considering pre-planning benefits."
        )
        self.rebuttal_handled: bool = False
        self.chatbot_response: Response | None = None
        super().__init__()
        self.awaits_user_input = False

    async def get_next_utterance(
        self,
        context: "UnderstandingContext",
        user_message: str,
        background_tasks: BackgroundTasks,
        lead_data: dict | None = None,
        conversation_id: UUID | None = None,
    ) -> Response:
        """Get the next utterance.

        Returns:
            The rebuttal response for the user's objection
        """
        if not self.chatbot_response:
            return Response(
                intent_name="rebuttal_flow",
                utterance_name="objection_not_understood",
                utterance_content="I'm sorry, I didn't understand what you said. Could you please rephrase it?",
            )

        self.rebuttal_handled = True

        await sleep(1)  # Simulate a brief pause for realism
        return self.chatbot_response

    def is_flow_complete(self) -> bool:
        """Check if the flow is complete."""
        return self.rebuttal_handled

    @staticmethod
    def get_conversation_status() -> ConversationStatus:
        """Get the conversation status based on rebuttal flow state."""
        return ConversationStatus.REBUTTAL

    @staticmethod
    def get_lead_status() -> LeadStatus | None:
        """Get the lead status based on rebuttal flow state."""
        return None


class FlowStack:
    """A stack of conversation flows."""

    def __init__(self) -> None:
        """Initialize the flow stack."""
        self.flows: list[Flow] = []

    @property
    def current_flow(self) -> Flow | None:
        """Get the current flow from the stack."""
        return self.flows[-1] if self.flows else None

    def push(self, flow: Flow) -> None:
        """Push a flow to the stack."""
        self.flows.append(flow)

    def pop(self) -> Flow | None:
        """Pop a flow from the stack."""
        return self.flows.pop() if self.flows else None

    def is_empty(self) -> bool:
        """Check if the flow stack is empty."""
        return not self.flows


FLOW_REGISTRY: dict[str, Flow] = {
    "intro_flow": IntroFlow(),
    "booking_flow": BookingFlow(),
    "resignation_flow": ResignationFlow(),
    "question_flow": QuestionFlow(),
    "repetition_flow": RepetitionFlow(),
    "rebuttal_flow": RebuttalFlow(),
}
