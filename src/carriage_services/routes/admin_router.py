import csv
import io
import json
import tempfile
from collections.abc import Iterator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from carriage_services.database import Conversation, ConversationContext, Error, Log, convert_entry_to_dict, get_db
from carriage_services.database.actions import list_active_call_sids
from carriage_services.interface.telephony import TwilioClient
from carriage_services.utils.enums import ConversationStatus, LeadStatus
from carriage_services.utils.twilio_downloader import TwilioRecordingDownloader

admin_router = APIRouter()
twilio_client = TwilioClient()


def stream_csv(db_query: Query, columns: list[str]) -> Iterator[str]:
    """
    A generator function that streams the results of a SQLAlchemy query as CSV rows.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    writer.writerow(columns)
    buffer.seek(0)
    yield buffer.read()
    buffer.seek(0)
    buffer.truncate(0)

    for item in db_query.yield_per(100):
        writer.writerow([getattr(item, col) for col in columns])
        buffer.seek(0)
        yield buffer.read()
        buffer.seek(0)
        buffer.truncate(0)


@admin_router.get("/export/{table_name}")
def export_table_to_csv(
    table_name: str,
    db: Session = Depends(get_db),  # noqa: B008
) -> StreamingResponse:
    """
    Exports data from the specified table ('conversations', 'logs', 'errors', or 'conversation_contexts') to a CSV file.
    """
    if table_name == "conversations":
        model = Conversation
    elif table_name == "logs":
        model = Log
    elif table_name == "errors":
        model = Error
    elif table_name == "conversation_contexts":
        model = ConversationContext
    else:
        raise HTTPException(status_code=404, detail="Table not found.")

    query = db.query(model)
    columns = [c.name for c in model.__table__.columns]
    filename = f"{table_name}_export.csv"

    response = StreamingResponse(
        stream_csv(query, columns),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
    return response


@admin_router.get("/conversation/status/{call_sid}")
def get_conversation_status_by_call_sid(
    call_sid: str,
    db: Session = Depends(get_db),  # noqa: B008
) -> dict[str, Any]:
    """
    Returns the status information for a conversation by its Twilio call SID.

    Args:
        call_sid: The Twilio call SID to look up
        db: Database session dependency

    Returns:
        Dictionary containing:
        - call_sid: The Twilio call SID
        - lead_status: The lead status from the database
        - is_active: Boolean indicating if the call is currently active in Twilio
    """
    conversation = db.query(Conversation).filter(Conversation.call_sid == call_sid).first()
    lead_status = LeadStatus.UNKNOWN.value if not conversation else conversation.lead_status.value
    twilio_state = twilio_client.check_twilio_call_active(call_sid)

    return {
        "call_sid": call_sid,
        "lead_status": lead_status,
        "is_active": twilio_state,
    }


@admin_router.get("/conversation/logs/latest/{user_id}")
def get_latest_conversation_logs(
    user_id: str,
    db: Session = Depends(get_db),  # noqa: B008
) -> dict[str, Any]:
    """
    Returns the logs of the most recent conversation for a given user ID.

    Args:
        user_id: The user ID to look up the latest conversation logs for
        db: Database session dependency

    Returns:
        Dictionary containing the latest conversation logs
    """
    latest_conversation = (
        db.query(Conversation).filter(Conversation.user_id == user_id).order_by(Conversation.updated_at.desc()).first()
    )

    if not latest_conversation:
        raise HTTPException(status_code=404, detail=f"No conversations found for user_id: {user_id}")

    logs = db.query(Log).filter(Log.conversation_id == latest_conversation.id).order_by(Log.timestamp.asc()).all()

    return {
        "status": latest_conversation.status,
        "lead_status": latest_conversation.lead_status,
        "logs": [convert_entry_to_dict(log) for log in logs],
    }


@admin_router.get("/conversation/logs/{conversation_id}")
def get_conversation_logs(
    conversation_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> dict[str, Any]:
    """
    Returns the logs of a specific conversation by its ID.

    Args:
        conversation_id: The ID of the conversation to look up logs for
        db: Database session dependency

    Returns:
        Dictionary containing the conversation logs
    """
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()

    if not conversation:
        raise HTTPException(status_code=404, detail=f"Conversation not found with ID: {conversation_id}")

    logs = db.query(Log).filter(Log.conversation_id == conversation.id).order_by(Log.timestamp.asc()).all()

    return {
        "status": conversation.status,
        "lead_status": conversation.lead_status,
        "logs": [convert_entry_to_dict(log) for log in logs],
    }


@admin_router.get("/conversation/logs/sid/{call_sid}")
def get_conversation_logs_by_sid(
    call_sid: str,
    db: Session = Depends(get_db),  # noqa: B008
) -> dict[str, Any]:
    """
    Returns the logs of a conversation by its Twilio call SID.

    Args:
        call_sid: The Twilio call SID to look up the conversation and logs for
        db: Database session dependency

    Returns:
        Dictionary containing the conversation logs
    """
    conversation = db.query(Conversation).filter(Conversation.call_sid == call_sid).first()

    if not conversation:
        raise HTTPException(status_code=404, detail=f"No conversation found with call_sid: {call_sid}")

    logs = db.query(Log).filter(Log.conversation_id == conversation.id).order_by(Log.timestamp.asc()).all()

    return {
        "conversation_id": str(conversation.id),
        "call_sid": call_sid,
        "user_id": conversation.user_id,
        "status": conversation.status,
        "lead_status": conversation.lead_status,
        "logs": [convert_entry_to_dict(log) for log in logs],
    }


@admin_router.get("/active")
def get_active_calls() -> dict[str, list[str]]:
    """
    Returns a list of all active calls from the database and Twilio.
    """
    active_in_twilio = set(twilio_client.list_active_calls())
    return {"active_calls": sorted(active_in_twilio)}


@admin_router.get("/statuses")
def get_available_statuses() -> dict[str, list[str]]:
    """
    Returns a list of all available conversation and lead statuses.
    """
    return {
        "conversation_statuses": [status.value for status in ConversationStatus],
        "lead_statuses": [status.value for status in LeadStatus],
    }


@admin_router.get("/metrics", response_class=PlainTextResponse)
def get_metrics(
    db: Session = Depends(get_db),  # noqa: B008
) -> str:
    """
    Returns key metrics in a Prometheus-friendly format.
    """
    metrics = []

    # Conversation Status Counts
    metrics.append("# HELP carriage_services_conversation_status_total Total number of conversations by status.")
    metrics.append("# TYPE carriage_services_conversation_status_total gauge")
    status_counts = db.query(Conversation.status, func.count(Conversation.status)).group_by(Conversation.status).all()
    for status, count in status_counts:
        metrics.append(f'carriage_services_conversation_status_total{{status="{status.value}"}} {count}')
    total_conversations = sum(count for _, count in status_counts)
    metrics.append(f'carriage_services_conversation_status_total{{status="total"}} {total_conversations}')

    metrics.append("")

    # Lead Status Counts
    metrics.append("# HELP carriage_services_lead_status_total Total number of conversations by lead status.")
    metrics.append("# TYPE carriage_services_lead_status_total gauge")
    lead_status_counts = (
        db.query(Conversation.lead_status, func.count(Conversation.lead_status))
        .group_by(Conversation.lead_status)
        .all()
    )
    for lead_status, count in lead_status_counts:
        metrics.append(f'carriage_services_lead_status_total{{lead_status="{lead_status.value}"}} {count}')
    total_leads = sum(count for _, count in lead_status_counts)
    metrics.append(f'carriage_services_lead_status_total{{lead_status="total"}} {total_leads}')

    metrics.append("")

    # Active Calls
    metrics.append("# HELP carriage_services_active_calls_total Total number of active calls by source.")
    metrics.append("# TYPE carriage_services_active_calls_total gauge")
    metrics.append(f'carriage_services_active_calls_total{{source="database"}} {len(list_active_call_sids(db))}')
    metrics.append(f'carriage_services_active_calls_total{{source="twilio"}} {len(twilio_client.list_active_calls())}')

    return "\n".join(metrics) + "\n"


@admin_router.get("/active/{call_sid}", response_class=JSONResponse)
def is_call_active(
    call_sid: str,
) -> JSONResponse:
    """
    Checks if a call is active in Twilio.
    """
    twilio_state = twilio_client.check_twilio_call_active(call_sid)
    return JSONResponse(
        content={
            "is_active": twilio_state,
        }
    )


@admin_router.get("/unsuccessful-bookings")
def get_unsuccessful_bookings(
    db: Session = Depends(get_db),  # noqa: B008
) -> dict[str, Any]:
    """
    Returns all conversations with unsuccessful booking attempts.

    Returns:
        Dictionary containing unsuccessful booking information
    """
    # Query all conversation contexts that contain unsuccessful booking data
    contexts = db.query(ConversationContext).all()

    unsuccessful_bookings = []
    for context in contexts:
        try:
            context_data = json.loads(context.context_data)
            if "unsuccessful_booking" in context_data:
                # Get conversation details
                conversation = db.query(Conversation).filter(Conversation.id == context.conversation_id).first()

                booking_info = context_data["unsuccessful_booking"]
                unsuccessful_bookings.append(
                    {
                        "conversation_id": str(context.conversation_id),
                        "call_sid": conversation.call_sid if conversation else None,
                        "user_id": conversation.user_id if conversation else None,
                        "lead_id": booking_info.get("lead_id"),
                        "requested_datetime": booking_info.get("requested_datetime"),
                        "failure_reason": booking_info.get("failure_reason"),
                        "timestamp": booking_info.get("timestamp"),
                        "lead_info": booking_info.get("lead_info"),
                        "conversation_status": conversation.status.value if conversation else None,
                        "lead_status": conversation.lead_status.value if conversation else None,
                    }
                )
        except (json.JSONDecodeError, KeyError):
            # Skip contexts that don't have valid JSON or unsuccessful_booking data
            continue

    return {"unsuccessful_bookings": unsuccessful_bookings, "total_count": len(unsuccessful_bookings)}


@admin_router.get("/statistics/intro-message-versions")
def get_intro_message_version_statistics(
    db: Session = Depends(get_db),  # noqa: B008
) -> dict[str, Any]:
    """
    Returns statistics of conversations grouped by intro message version.
    Reads intro_message_version from conversation context data.

    Returns:
        Dictionary containing statistics for each intro message version
    """
    conversations_with_context = (
        db.query(Conversation, ConversationContext.context_data)
        .outerjoin(ConversationContext, Conversation.id == ConversationContext.conversation_id)
        .all()
    )

    statistics: dict[str, Any] = {}

    for conversation, context_data in conversations_with_context:
        intro_version = None

        if context_data:
            try:
                context_json = json.loads(context_data)
                intro_version = context_json.get("intro_message_version")
            except json.JSONDecodeError:
                # If context data is corrupted, treat as None
                pass

        version_key = intro_version if intro_version is not None else "null"

        if version_key not in statistics:
            statistics[version_key] = {
                "intro_message_version": intro_version,
                "total_conversations": 0,
                "conversation_statuses": {},
                "lead_statuses": {},
            }

        statistics[version_key]["total_conversations"] += 1

        status_value = conversation.status.value
        if status_value not in statistics[version_key]["conversation_statuses"]:
            statistics[version_key]["conversation_statuses"][status_value] = 0
        statistics[version_key]["conversation_statuses"][status_value] += 1

        lead_status_value = conversation.lead_status.value
        if lead_status_value not in statistics[version_key]["lead_statuses"]:
            statistics[version_key]["lead_statuses"][lead_status_value] = 0
        statistics[version_key]["lead_statuses"][lead_status_value] += 1

    return {"statistics_by_intro_message_version": statistics, "total_versions": len(statistics)}


@admin_router.get("/recordings/download/{call_sid}")
def download_recordings_by_call_sid(call_sid: str) -> FileResponse:
    """
    Download Twilio call recording for a specific call SID.

    Args:
        call_sid: The Twilio call SID to download recording for

    Returns:
        FileResponse with the audio file
    """
    downloader = TwilioRecordingDownloader()
    recording = downloader.get_recordings_data_for_call_sid(call_sid)

    if not recording:
        raise HTTPException(status_code=404, detail="No recordings found for the specified call SID.")

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    temp_file.write(recording["content"])
    temp_file.close()

    return FileResponse(
        path=temp_file.name,
        filename=recording["filename"],
        media_type="audio/wav",
        headers={"Content-Disposition": f'attachment; filename="{recording["filename"]}"'},
    )
