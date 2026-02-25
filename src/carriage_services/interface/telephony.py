import time
from typing import cast

from loguru import logger
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client
from twilio.rest.api.v2010.account.call import CallInstance
from twilio.twiml.voice_response import Gather, VoiceResponse

from carriage_services.conversation.flows import BookingFlow
from carriage_services.conversation.runner import Runner
from carriage_services.interface.base import Interface
from carriage_services.settings import settings
from carriage_services.tts.tts import TTSService


class TwilioClient(Interface):
    """Handles interactions with the Twilio telephony provider."""

    @staticmethod
    def _render_messages(
        target: VoiceResponse | Gather,
        messages: list[str],
        voice: str,
        language: str,
    ) -> None:
        for message_item in messages:
            if message_item.startswith("http://") or message_item.startswith("https://"):
                target.play(message_item, loop=1)
            else:
                target.say(message_item, voice=voice, language=language)

    def __init__(self) -> None:
        """Initializes the Twilio client."""
        self.client = Client(settings.telephony.TWILIO_ACCOUNT_SID, settings.telephony.TWILIO_AUTH_TOKEN)
        self.base_url = settings.telephony.BASE_URL

        self.voice = settings.telephony.TWILIO_TTS_VOICE
        self.language = "en-US"

    def create(self, to_number: str, from_number: str | None = None, record: bool = False) -> CallInstance:
        """
        Creates an outbound call using Twilio.

        Args:
            to_number: The destination phone number in E.164 format.
            from_number: The Twilio phone number to use for the call.
                        If not provided, uses the default phone number.
            record: Whether to record the call.

        Returns:
            The created Twilio CallInstance.
        """
        # Use provided from_number or fall back to default
        caller_number = from_number or settings.telephony.default_phone_number
        if not caller_number:
            raise ValueError("No Twilio phone number available. Set TWILIO_PHONE_NUMBERS in your .env file.")

        webhook_url = f"{self.base_url}/voice"
        status_callback_url = f"{self.base_url}/status"
        return self.client.calls.create(
            to=to_number,
            from_=caller_number,
            url=webhook_url,
            status_callback=status_callback_url,
            status_callback_event=["completed", "busy", "failed", "no-answer", "canceled"],
            record=record,
        )

    def send_message(
        self,
        messages: list[str],
        call_sid: str = "",
        is_running: bool = True,
        barge_in: bool = True,
    ) -> str:
        """Initializes a call with a greeting message.

        Args:
            call_sid: The unique identifier for the call.
            messages: The list of messages to be played.
            is_running: A flag indicating if the conversation is still active.
            barge_in: Whether the user can interrupt the bot while it is speaking.

        Returns:
            A Twilio VoiceResponse object containing the TwiML instructions.
        """
        response = VoiceResponse()

        if not is_running:
            # Remove gather and add hangup directly to the response
            self._render_messages(response, messages, self.voice, self.language)

            response.hangup()
            logger.info("Conversation ended, hanging up the call.")

        else:
            action_url = f"{self.base_url}/gather?call_sid={call_sid}"
            timeout_url = f"{self.base_url}/timeout?call_sid={call_sid}"
            noise_url = (
                f"{self.base_url}/static-recordings/{settings.telephony.COMFORT_NOISE_FILENAME}?v={int(time.time())}"
            )
            # Speech hints for funeral industry terms to improve recognition accuracy
            _speech_hints = [
                "preplanning",
                "bot",
                "funeral home",
                "cremation",
                "burial",
                "casket",
                "urn",
                "appointment",
                "in-person",
                "seminar",
                "human",
                "agent",
                "representative",
                "real person",
                "payment plan",
                "life insurance",
                "veteran",
                "affordable",
                "expensive",
                "budget",
                "address",
                "location",
                "overwhelmed",
                "morbid",
                "sensitive",
                "do not call",
            ]

            # Setting barge_in option to False in response.gather() does not seem to work reliably,
            # changing the logic to sequential processing seems to be very reliable
            if not barge_in:
                self._render_messages(response, messages, self.voice, self.language)

            # timeout must be long enough to cover dynamics api delays
            gather = response.gather(
                input="speech",
                action=action_url,
                method="POST",
                language=self.language,
                speech_timeout="auto",
                timeout=settings.telephony.TIMEOUT,
                enhanced=True,
                hints=",".join(_speech_hints),  # hints do not work with nova-3 but work with nova-2
                # TODO:
                # - check nova-2/nova-3 wrt. WER vs. latency (also nova-2-phonecall)
                # - check if upgrading twilio fixes nova-3 hints issues, or if nova-3 needs different hint formatting
                # speech_model="deepgram_nova-3",
                speech_model="phone_call",
            )

            response.redirect(timeout_url, method="POST")

            if barge_in:
                self._render_messages(gather, messages, self.voice, self.language)

            if settings.telephony.ENABLE_COMFORT_NOISE:
                gather.play(noise_url, loop=0)

        return str(response)

    @staticmethod
    def receive_message(form: dict | None = None) -> tuple[str, float]:
        """Processes the speech-to-text result from Twilio's webhook.

        Args:
            form: The form data received from Twilio containing the transcription and confidence.

        Returns:
            A tuple of (transcribed text, confidence score). Returns ("", 0.0) if no data available.
        """
        if form is None:
            return "", 0.0
        transcription_value = form.get("SpeechResult")
        confidence_value = form.get("Confidence", 0.0)
        transcription = transcription_value if isinstance(transcription_value, str) else ""

        # Convert confidence to float if it's a string
        if isinstance(confidence_value, str):
            try:
                confidence = float(confidence_value)
            except ValueError:
                confidence = 0.0
        else:
            confidence = float(confidence_value) if confidence_value else 0.0

        logger.info("Received transcription: {} with confidence: {}", transcription, confidence)
        return transcription, confidence

    def check_twilio_call_active(self, call_sid: str) -> bool:
        """Checks if a call is active via the Twilio API."""
        try:
            call = self.client.calls(call_sid).fetch()
            return call.status in ["queued", "ringing", "in-progress"]
        except TwilioRestException as e:
            if e.status == 404:
                logger.warning(f"Call SID {call_sid} not found in Twilio.")
            else:
                logger.error(f"Twilio API error checking call status for {call_sid}: {e}")
            return False

    def list_active_calls(self) -> list[str]:
        """Lists all active calls from the Twilio API."""
        active_sids = []
        try:
            for status in ["queued", "ringing", "in-progress"]:
                calls = self.client.calls.list(status=status)
                active_sids.extend([call.sid for call in calls])
            return active_sids
        except TwilioRestException as e:
            logger.error(f"Twilio API error listing active calls: {e}")
            return []

    def transfer_call(self, call_sid: str, to_number: str, messages: list[str] | None = None) -> None:
        """Transfers the call to a new number."""
        logger.info(f"Transferring call {call_sid} to {to_number}")
        response = VoiceResponse()
        if messages:
            for message in messages:
                response.play(message, loop=1)
        response.dial(to_number)
        twiml = str(response)
        try:
            self.client.calls(call_sid).update(twiml=twiml)
        except Exception as e:
            logger.error(f"Failed to transfer call: {e}")

    def end_call_gracefully(self, call_sid: str) -> None:
        """Gracefully end a call with optional final message and proper cleanup."""
        try:
            # Check if call is still active before attempting to update
            if not self.check_twilio_call_active(call_sid):
                logger.info(f"Call {call_sid} already ended, skipping graceful hangup")
                return

            response = VoiceResponse()
            response.hangup()

            self.client.calls(call_sid).update(twiml=str(response))
            logger.info(f"Call {call_sid} ended gracefully")
        except Exception as e:
            logger.warning(f"Failed to end call {call_sid} gracefully: {e}")

    def create_background_response(
        self, tts_service: TTSService, current_slot_or_flow_name: str, filler_word_counter: int
    ) -> str:
        """Creates a TwiML response that plays appropriate sound while processing based on flow type."""
        response = VoiceResponse()

        if current_slot_or_flow_name in settings.telephony.FLOW_INTERRUPTION_SETTINGS:
            if current_slot_or_flow_name == "question_flow_completed":
                urls = [
                    tts_service.get_recording_url(
                        "question_flow_completed", self.get_next_filler_word(filler_word_counter)
                    ),
                    f"{self.base_url}/static-recordings/computer-keyboard-typing.mp3?v={int(time.time())}",
                ]
            elif current_slot_or_flow_name == "booking_flow_completed":
                urls = [
                    tts_service.get_recording_url(
                        "booking_flow_completed", self.get_next_filler_word(filler_word_counter)
                    ),
                    f"{self.base_url}/static-recordings/computer-keyboard-typing.mp3?v={int(time.time())}",
                ]
            else:
                urls = [
                    tts_service.get_recording_url("booking_flow", self.get_next_filler_word(filler_word_counter)),
                    f"{self.base_url}/static-recordings/computer-keyboard-typing.mp3?v={int(time.time())}",
                ]
        elif current_slot_or_flow_name == "resignation_goodbye":
            urls = []
        else:
            urls = [
                tts_service.get_recording_url(current_slot_or_flow_name, self.get_next_filler_word(filler_word_counter))
            ]

        for url in urls:
            response.play(url)

        # Only redirect to background_complete if interruption is not allowed
        allow_interruption = settings.telephony.FLOW_INTERRUPTION_SETTINGS.get(current_slot_or_flow_name, False)
        if not allow_interruption:
            response.redirect(f"{self.base_url}/background_complete", method="POST")

        return str(response)

    @staticmethod
    def get_next_filler_word(counter: int) -> str:
        """Get the next filler word in sequence based on the provided counter."""
        num_options = settings.conversation.NUMBER_OF_FILLER_WORDS_OPTIONS
        word_index = ((counter - 1) % num_options) + 1  # type: ignore
        return f"filler_word_{word_index}"


def get_current_slot_or_flow_name_for_filler_words(runner: Runner, confidence: float, transcription: str) -> str:
    """Get the name of the current slot or flow."""
    if confidence < settings.conversation.TRANSCRIPTION_CONFIDENCE_THRESHOLD:
        return "repetition_flow"

    current_flow = runner.flow_stack.current_flow
    current_flow_name = "intro_flow"

    if current_flow:
        current_flow_name = current_flow.name
        try:
            current_slot_name = current_flow.get_active_slot().name
        except IndexError:
            if current_flow_name == "booking_flow":
                current_flow = cast(BookingFlow, current_flow)
                current_slot_name = "booking_flow_completed" if current_flow.booking_made is True else "booking_flow"
            else:
                current_slot_name = "booking_flow"

    if (
        current_slot_name == "booking_flow_completed"
        or current_slot_name not in settings.telephony.FLOW_INTERRUPTION_SETTINGS
    ) and transcription.strip():
        is_question, question_confidence = runner.question_classifier.classify(transcription)
        if (
            is_question
            and question_confidence > settings.question_classification.QUESTION_CLASSIFICATION_CONFIDENCE_THRESHOLD
        ):
            return "question_flow_completed" if current_slot_name == "booking_flow_completed" else "question_flow"

    return current_slot_name


def should_allow_barge_in(runner: Runner) -> bool:
    """Return whether barge-in should be enabled based on the active flow."""
    current_flow = runner.flow_stack.current_flow
    return current_flow is None or current_flow.name != "booking_flow"
