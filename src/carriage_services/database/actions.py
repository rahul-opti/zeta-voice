import datetime
import json
import uuid
from typing import Any

from loguru import logger
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import DeclarativeBase, Session

from carriage_services.database.models import Conversation, ConversationContext, Error, Log
from carriage_services.utils import ConversationStatus, LogMessageSource


def create_log_entry(
    db: Session, conversation_id: uuid.UUID, message: str, source: LogMessageSource = LogMessageSource.BOT
) -> None:
    """Helper function to create and save a log entry."""
    log = Log(
        conversation_id=conversation_id,
        message=message,
        source=source,
        timestamp=datetime.datetime.now(datetime.UTC),  # type: ignore
    )
    db.add(log)
    db.commit()
    logger.info(f"Logged for Conversation ID {str(conversation_id)} ({source.value}): {message}")


def convert_entry_to_dict(entry: DeclarativeBase) -> dict:
    """Convert a Log entry to a dictionary format."""
    return {c.name: getattr(entry, c.name) for c in entry.__table__.columns}


def create_error_entry(
    db: Session,
    error_message: str,
    function_name: str,
    exception_type: str,
    conversation_id: uuid.UUID,
    stack_trace: str,
) -> None:
    """Helper function to create and save an error entry."""
    error = Error(
        error_message=error_message,
        function_name=function_name,
        exception_type=exception_type,
        conversation_id=conversation_id,
        stack_trace=stack_trace,
    )
    db.add(error)
    db.commit()
    logger.info(f"Error logged for function {function_name}: {error_message}")


def upsert_conversation_context(db: Session, conversation_id: uuid.UUID, context_data: dict[str, Any]) -> None:
    """
    Creates or updates the full context for a conversation while preserving special data.
    This performs an 'upsert' operation: it inserts a new row if one doesn't exist
    for the conversation_id, or updates the existing one if it does.

    Special data like 'unsuccessful_booking' is preserved from the existing context.
    """
    # Check for existing context to preserve special data
    instance = db.query(ConversationContext).filter_by(conversation_id=conversation_id).first()

    if instance:
        try:
            existing_data = json.loads(instance.context_data)
            # Preserve special data like unsuccessful_booking
            special_keys = ["unsuccessful_booking"]
            for key in special_keys:
                if key in existing_data and key not in context_data:
                    context_data[key] = existing_data[key]
        except json.JSONDecodeError:
            # If existing data is corrupted, continue with new data
            pass

    context_json = json.dumps(context_data, default=str)

    if db.bind.dialect.name == "postgresql":
        stmt = insert(ConversationContext).values(
            conversation_id=conversation_id,
            context_data=context_json,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["conversation_id"],
            set_={"context_data": stmt.excluded.context_data},
        )
        db.execute(stmt)
        db.commit()
        logger.info(f"Upserted context for Conversation ID {conversation_id}")
    else:
        if instance:
            instance.context_data = context_json
        else:
            instance = ConversationContext(conversation_id=conversation_id, context_data=context_json)
            db.add(instance)
        db.commit()
        logger.info(f"Upserted context for Conversation ID {conversation_id}")


def merge_conversation_context(db: Session, conversation_id: uuid.UUID, additional_data: dict[str, Any]) -> None:
    """
    Merges additional data with existing conversation context without overwriting.
    This is useful for adding specific data (like unsuccessful bookings) that should persist
    even when the main context gets updated later.
    """
    # Get existing context
    instance = db.query(ConversationContext).filter_by(conversation_id=conversation_id).first()

    if instance:
        # Merge with existing context
        try:
            existing_data = json.loads(instance.context_data)
            # Merge the additional data - this preserves existing data and adds new
            existing_data.update(additional_data)
            context_json = json.dumps(existing_data, default=str)
        except json.JSONDecodeError:
            # If existing data is corrupted, use additional data as base
            context_json = json.dumps(additional_data, default=str)

        instance.context_data = context_json
        db.commit()
        logger.info(f"Merged additional data into existing context for Conversation ID {conversation_id}")
    else:
        # Create new context with additional data
        context_json = json.dumps(additional_data, default=str)
        instance = ConversationContext(conversation_id=conversation_id, context_data=context_json)
        db.add(instance)
        db.commit()
        logger.info(f"Created new context with additional data for Conversation ID {conversation_id}")


def check_database_call_sid_active(db: Session, call_sid: str) -> bool:
    """Checks if a call_sid exists and has an active status in the database."""
    active_statuses = [ConversationStatus.CALLING, ConversationStatus.ANSWERED]
    count = (
        db.query(Conversation)
        .filter(Conversation.call_sid == call_sid, Conversation.status.in_(active_statuses))
        .count()
    )
    return count > 0


def list_active_call_sids(db: Session) -> list[str]:
    """Lists all call SIDs with an active status from the database."""
    active_statuses = [ConversationStatus.CALLING, ConversationStatus.ANSWERED]
    query = db.query(Conversation.call_sid).filter(Conversation.status.in_(active_statuses))
    return [row.call_sid for row in query if row.call_sid]


def get_conversation_by_call_sid(db: Session, call_sid: str) -> Conversation | None:
    """Get conversation by call_sid."""
    return db.query(Conversation).filter(Conversation.call_sid == call_sid).first()


def get_conversation_context(db: Session, conversation_id: uuid.UUID) -> dict[str, Any] | None:
    """Get conversation context by conversation ID."""
    context_entry = db.query(ConversationContext).filter(ConversationContext.conversation_id == conversation_id).first()
    if context_entry:
        import json

        return json.loads(context_entry.context_data)
    return None
