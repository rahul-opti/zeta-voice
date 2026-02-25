import asyncio
from enum import Enum
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from fastapi.responses import PlainTextResponse
from loguru import logger
from sqlalchemy.orm import Session

from carriage_services.auth import user_api_key_auth
from carriage_services.conversation.runner import OutputType, Runner, StartCallRequest, VoiceName
from carriage_services.database import get_db
from carriage_services.database.actions import get_conversation_by_call_sid, get_conversation_context
from carriage_services.interface.telephony import TwilioClient, should_allow_barge_in
from carriage_services.orchestration.telephony_orchestrator import TelephonyOrchestrator
from carriage_services.settings import ConversationSettings, TelephonySettings

router = APIRouter()
client = TwilioClient()

settings = ConversationSettings()
telephony_settings = TelephonySettings()


def _create_from_number_enum():  # type: ignore  # noqa: ANN202
    """Create FromNumber enum from available Twilio phone numbers for dropdown in Swagger UI."""
    phone_numbers: list[str] = telephony_settings.available_phone_numbers  # type: ignore[assignment]
    if not phone_numbers:
        return Enum("FromNumber", {"NONE": "none"}, type=str)

    enum_members = {}
    for number in phone_numbers:  # type: ignore[attr-defined]
        # Use the phone number itself as both key and value for cleaner display
        safe_key = number.replace("+", "PLUS_").replace("-", "_")
        enum_members[safe_key] = number

    return Enum("FromNumber", enum_members, type=str)


FromNumber = _create_from_number_enum()

_active_runners: dict[str, Runner] = {}
_pending_responses: dict[str, str] = {}

orchestrator = TelephonyOrchestrator(client, telephony_settings, settings, _active_runners, _pending_responses)


def get_or_create_runner(call_sid: str, voice_name: str | None = None, db: Session | None = None) -> Runner:
    """
    Get an existing runner for a call_sid or create a new one.
    If call_sid is None, creates a new runner without storing it.
    If voice_name is None and call_sid exists, tries to retrieve voice_name from database.
    """
    if call_sid is None:
        logger.debug("Creating temporary runner (no call_sid provided)")
        return Runner(settings, voice_name)

    if call_sid not in _active_runners:
        # If voice_name is not provided and we have db access, try to get it from context
        if voice_name is None and db is not None:
            conversation = get_conversation_by_call_sid(db, call_sid)
            if conversation:
                context_data = get_conversation_context(db, conversation.id)
                if context_data:
                    voice_name = context_data.get("voice_name")
                    logger.debug(f"Retrieved voice_name '{voice_name}' from context for call_sid: {call_sid}")

        if voice_name is not None:
            logger.info(f"Creating new runner for call_sid: {call_sid}")
            _active_runners[call_sid] = Runner(settings, voice_name)
        else:
            logger.warning("Error retrieving voice_name from context")
            raise ValueError("Voice name could not be determined")
    else:
        logger.debug(f"Using existing runner for call_sid: {call_sid}")

    return _active_runners[call_sid]


@router.get("/runners", dependencies=[Depends(user_api_key_auth)])
async def get_runners_status() -> dict[str, Any]:
    """Get the status of all active runners (useful for debugging)."""
    return {"active_runners_count": len(_active_runners), "active_call_sids": list(_active_runners.keys())}


@router.post("/start_call", dependencies=[Depends(user_api_key_auth)])
async def start_call(
    payload: StartCallRequest,
    db: Annotated[Session, Depends(get_db)],
    background_tasks: BackgroundTasks,
    from_number: Annotated[  # type: ignore[valid-type]
        FromNumber | None,
        Query(
            description="The Twilio phone number to use for the outbound call. "
            "If not selected, uses the first available number.",
        ),
    ] = None,
    record_call: bool = True,
    voice_name: VoiceName = VoiceName.MARIA,  # type: ignore[valid-type]
) -> dict[str, Any]:
    """
    API endpoint to initiate an outbound call by creating a conversation and delegating to the MemoryService.
    """
    # Extract the phone number string from the enum value
    selected_from_number = from_number.value if from_number else None  # type: ignore[union-attr]
    call_instance = client.create(
        to_number=payload.to_number,
        from_number=selected_from_number,
        record=record_call,
    )
    call_sid = call_instance.sid

    runner = get_or_create_runner(call_sid, voice_name.value)
    await runner.initialize_conversation(payload, db, background_tasks, OutputType.URL)
    return {"call_sid": call_sid}


@router.post("/voice", response_class=PlainTextResponse)
async def voice(
    request: Request, db: Annotated[Session, Depends(get_db)], background_tasks: BackgroundTasks
) -> Response:
    """Handles answered calls by delegating to MemoryService and responding with TwiML."""
    form = await request.form()
    call_sid = form.get("CallSid")
    logger.info(f"Voice webhook called for CallSid: {call_sid}")

    runner = get_or_create_runner(str(call_sid), db=db)

    # Wait for initialization to complete before starting conversation
    await runner.initialization_event.wait()

    message = await runner.start_conversation(str(call_sid), background_tasks, output_type=OutputType.URL)

    response = client.send_message(
        message,
        call_sid=str(call_sid),
        barge_in=should_allow_barge_in(runner),
    )

    await asyncio.sleep(telephony_settings.FIRST_MESSAGE_DELAY_SECONDS)
    logger.info(f"Adding delay of {telephony_settings.FIRST_MESSAGE_DELAY_SECONDS} seconds before first message")

    runner.set_first_message_sent_time()

    while runner.flow_stack.is_empty():
        await asyncio.sleep(0.1)
    return PlainTextResponse(response, media_type="text/xml")


@router.post("/status", response_class=PlainTextResponse)
async def call_status_webhook(request: Request) -> Response:
    """Handles call status changes including hangup events."""
    form = await request.form()
    call_sid = str(form.get("CallSid", ""))
    call_status = str(form.get("CallStatus", ""))

    logger.info(f"Call status webhook: CallSid={call_sid}, Status={call_status}")

    if call_status in ["completed", "busy", "failed", "no-answer", "canceled"]:
        logger.info(f"Call {call_sid} terminated with status: {call_status}")
        orchestrator.cleanup_runner(call_sid)

    return PlainTextResponse("", media_type="text/xml")


@router.post("/gather", response_class=PlainTextResponse)
async def gather(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Receives and processes the speech-to-text result via the TelephonyOrchestrator."""
    form = await request.form()
    call_sid = str(form.get("CallSid"))
    transcription, confidence = client.receive_message(dict(form))
    runner = get_or_create_runner(call_sid, db=db)

    return await orchestrator.handle_gather(call_sid, transcription, confidence, runner, background_tasks)


@router.post("/timeout", response_class=PlainTextResponse)
async def timeout(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Handles timeout when no user input is detected."""
    form = await request.form()
    call_sid = str(form.get("CallSid"))

    logger.info(f"Timeout webhook called for CallSid: {call_sid} - no user input detected")

    runner = get_or_create_runner(call_sid, db=db)

    # Treat timeout as empty transcription to trigger a response instead of ending call
    return await orchestrator.handle_gather(call_sid, "", 0.0, runner, background_tasks)


@router.post("/background_complete", response_class=PlainTextResponse)
async def background_complete(request: Request) -> Response:
    """Handles completion of background sound and delivers the pending response."""
    form = await request.form()
    call_sid = str(form.get("CallSid"))

    while call_sid not in _pending_responses:
        await asyncio.sleep(0.1)

    response_twiml = _pending_responses.pop(call_sid)
    logger.info(f"Delivering queued response for call_sid: {call_sid}")
    return PlainTextResponse(response_twiml, media_type="text/xml")
