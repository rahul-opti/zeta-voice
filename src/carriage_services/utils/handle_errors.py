import datetime
import functools
import inspect
import traceback
from collections.abc import Callable
from typing import Any
from uuid import UUID

from loguru import logger
from sqlalchemy.orm import Session

from carriage_services.database import Conversation, create_error_entry
from carriage_services.utils import ConversationStatus


def handle_errors(
    db_session: Session,
    conversation_id: UUID,
) -> Callable:
    """
    Decorator for saving errors to database and updating conversation status.

    Args:
        db_session: Database session for saving errors
        conversation_id: Conversation ID for linking error logs

    Returns:
        Decorated function
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {func.__name__}: {str(e)}")
                try:
                    # Save error to database
                    create_error_entry(
                        db=db_session,
                        error_message=str(e),
                        function_name=func.__name__,
                        exception_type=type(e).__name__,
                        conversation_id=conversation_id,
                        stack_trace=traceback.format_exc(),
                    )
                    # Update conversation status to ERROR
                    conversation = db_session.query(Conversation).filter(Conversation.id == conversation_id).first()
                    if conversation:
                        conversation.status = ConversationStatus.ERROR
                        conversation.updated_at = datetime.datetime.now(datetime.UTC)  # type: ignore
                        db_session.commit()
                except Exception as db_error:
                    logger.error(f"Failed to save error to database or update conversation status: {db_error}")
                raise e

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {func.__name__}: {str(e)}")
                try:
                    # Save error to database
                    create_error_entry(
                        db=db_session,
                        error_message=str(e),
                        function_name=func.__name__,
                        exception_type=type(e).__name__,
                        conversation_id=conversation_id,
                        stack_trace=traceback.format_exc(),
                    )
                    # Update conversation status to ERROR
                    conversation = db_session.query(Conversation).filter(Conversation.id == conversation_id).first()
                    if conversation:
                        conversation.status = ConversationStatus.ERROR
                        conversation.updated_at = datetime.datetime.now(datetime.UTC)  # type: ignore
                        db_session.commit()
                except Exception as db_error:
                    logger.error(f"Failed to save error to database or update conversation status: {db_error}")
                raise e

        # Check if the function is async and return appropriate wrapper
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator
