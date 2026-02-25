import asyncio

from fastapi import BackgroundTasks
from fastapi.responses import PlainTextResponse, Response
from loguru import logger

from carriage_services.conversation.models import Action, SetSlotAction
from carriage_services.conversation.runner import OutputType, Runner
from carriage_services.interface.telephony import (
    TwilioClient,
    get_current_slot_or_flow_name_for_filler_words,
    should_allow_barge_in,
)
from carriage_services.settings import ConversationSettings, TelephonySettings


class TelephonyOrchestrator:
    """Orchestrates the telephony interaction, deciding when to use fillers."""

    def __init__(
        self,
        client: TwilioClient,
        telephony_settings: TelephonySettings,
        conversation_settings: ConversationSettings,
        active_runners: dict[str, Runner],
        pending_responses: dict[str, str],
    ):
        self.client = client
        self.telephony_settings = telephony_settings
        self.conversation_settings = conversation_settings

        self._active_runners = active_runners
        self._pending_responses = pending_responses

    async def handle_gather(
        self, call_sid: str, transcription: str, confidence: float, runner: Runner, background_tasks: BackgroundTasks
    ) -> Response:
        """
        Handles the gather webhook, deciding whether to respond immediately or use a filler.
        """
        current_flow = runner.flow_stack.current_flow
        # Check if user interrupted the initial message delivery or spoke before it, repeat it without filler words
        first_message_interrupted = runner.is_first_message_interrupted()
        if first_message_interrupted and runner.initial_message_object:
            logger.info("User interrupted first message or spoke before first message " "- repeating initial message")
            message = [url[1] for url in runner.initial_message_object.urls]
            response_twiml = self.client.send_message(
                message,
                call_sid=call_sid,
                is_running=runner.is_running,
                barge_in=should_allow_barge_in(runner),
            )
            return PlainTextResponse(response_twiml, media_type="text/xml")

        # Special handling for timeout scenarios (empty transcription with 0.0 confidence)
        # Process timeout immediately without filler words to avoid unnecessary delays
        if not transcription.strip() and confidence == 0.0:
            logger.info(f"Processing timeout response immediately for call_sid: {call_sid}, skipping filler.")
            response_twiml = await self._process_user_message(
                runner, call_sid, transcription, confidence, background_tasks, skip_understanding=False
            )
            return PlainTextResponse(response_twiml, media_type="text/xml")

        simple_result = None
        if len(transcription.split(" ")) <= self.conversation_settings.MAX_WORDS_FOR_SIMPLE_CLASSIFIER:
            simple_result = runner.rule_based_english_classifier.classify(transcription)

        # We process immediately ONLY if the response can be handled by the simple rule-based classifier.
        if (
            simple_result is not None
            and current_flow
            and current_flow.get_active_slots()
            and not first_message_interrupted
        ):
            logger.info(f"Processing simple response immediately for call_sid: {call_sid}, skipping filler.")

            # Create and run the action for the simple classification.
            active_slot = current_flow.get_active_slot()

            skip_understanding = False
            if simple_result == "goodbye" and (active_slot.name in ["decline_seminar", "accept_seminar_list"]):
                action = SetSlotAction(flow_name=current_flow.name, slot_name=active_slot.name, slot_value=True)
                action_obj = Action(action=action)
                runner.run_action(action_obj)
                skip_understanding = True
            elif isinstance(simple_result, bool):
                action = SetSlotAction(
                    flow_name=current_flow.name, slot_name=active_slot.name, slot_value=simple_result
                )
                action_obj = Action(action=action)
                runner.run_action(action_obj)
                skip_understanding = True
            elif simple_result == "who_is_this" and active_slot.name == "confirm_identity":
                skip_understanding = True

            if (active_slot.name in {"accept_appointment", "offer_rebuttal"}) and simple_result is True:
                return self.handle_time_consuming_response(
                    call_sid, transcription, confidence, runner, background_tasks, skip_understanding=True
                )

            # Get the next utterance, skipping the LLM understanding step since we've already handled it.
            response_twiml = await self._process_user_message(
                runner, call_sid, transcription, confidence, background_tasks, skip_understanding=skip_understanding
            )
            return PlainTextResponse(response_twiml, media_type="text/xml")
        else:
            return self.handle_time_consuming_response(
                call_sid, transcription, confidence, runner, background_tasks, skip_understanding=False
            )

    def handle_time_consuming_response(
        self,
        call_sid: str,
        transcription: str,
        confidence: float,
        runner: Runner,
        background_tasks: BackgroundTasks,
        skip_understanding: bool = False,
    ) -> Response:
        """Handles responses that may require LLM processing, using fillers if needed."""
        # For any ambiguous response that requires LLM analysis, use the filler.
        logger.info(f"Using filler and background task for ambiguous response from call_sid: {call_sid}")
        current_slot_or_flow_name = get_current_slot_or_flow_name_for_filler_words(runner, confidence, transcription)
        background_tasks.add_task(
            self.process_user_message,
            runner,
            call_sid,
            transcription,
            confidence,
            current_slot_or_flow_name,
            background_tasks,
            skip_understanding,
        )

        if call_sid not in self._pending_responses:
            # Increment the filler word counter and pass it to create_background_response
            runner.filler_word_counter += 1
            background_response = self.client.create_background_response(
                runner.tts_service, current_slot_or_flow_name, runner.filler_word_counter
            )
            return PlainTextResponse(background_response, media_type="text/xml")
        return PlainTextResponse("<Response></Response>", media_type="text/xml")

    def process_user_message(
        self,
        runner: Runner,
        call_sid: str,
        transcription: str,
        confidence: float,
        current_slot_or_flow_name: str,
        background_tasks: BackgroundTasks,
        skip_understanding: bool = False,
    ) -> None:
        """Processes the user's message in a background task."""

        async def _async_process() -> None:
            response_twiml = await self._process_user_message(
                runner, call_sid, transcription, confidence, background_tasks, skip_understanding
            )

            allow_interruption = self.telephony_settings.FLOW_INTERRUPTION_SETTINGS.get(
                current_slot_or_flow_name, False
            )
            if allow_interruption:
                try:
                    if self.client.check_twilio_call_active(call_sid) and not runner.transfer_to_human:
                        self.client.client.calls(call_sid).update(twiml=response_twiml)
                        logger.info(f"Response delivered immediately for call_sid: {call_sid}")
                    else:
                        logger.info(f"Call {call_sid} no longer active, skipping response delivery")
                except Exception as update_error:
                    logger.error(f"Failed to update call {call_sid}: {update_error}")
            else:
                self._pending_responses[call_sid] = response_twiml
                logger.info(f"Response queued for call_sid: {call_sid}")

        asyncio.run(_async_process())

    async def _process_user_message(
        self,
        runner: Runner,
        call_sid: str,
        transcription: str,
        confidence: float,
        background_tasks: BackgroundTasks,
        skip_understanding: bool = False,
    ) -> str:
        if not transcription or transcription.strip() == "":
            runner.no_transcription_count += 1
        else:
            runner.no_transcription_count = 0

        if runner.no_transcription_count > 0 and (not transcription or transcription.strip() == ""):
            logger.info(
                "Received {} empty transcriptions for call_sid: {}, ending conversation",
                runner.no_transcription_count,
                call_sid,
            )
            messages = await runner.handle_empty_transcription(output_type=OutputType.URL)
        else:
            messages = await runner.handle_single_message(
                transcription,
                background_tasks,
                confidence,
                output_type=OutputType.URL,
                skip_understanding=skip_understanding,
            )

        if runner.transfer_to_human:
            await self.transfer_call(runner, call_sid, messages)

        return self.client.send_message(
            messages,
            call_sid=call_sid,
            is_running=runner.is_running,
            barge_in=should_allow_barge_in(runner),
        )

    async def transfer_call(self, runner: Runner, call_sid: str, messages: list[str]) -> None:
        """Transfers the call to a human agent."""
        handoff_number = runner.handoff_number
        if handoff_number:
            self.client.transfer_call(call_sid, handoff_number, messages)

    def cleanup_runner(self, call_sid: str) -> None:
        """Removes a runner from the active runners."""
        if call_sid in self._active_runners:
            logger.info(f"Cleaning up runner for call_sid: {call_sid}")
            try:
                self.client.end_call_gracefully(call_sid)
            except Exception as e:
                logger.warning(f"Error during graceful call end for {call_sid}: {e}")
            finally:
                del self._active_runners[call_sid]
        else:
            logger.debug(f"Runner for call_sid {call_sid} already cleaned up")
