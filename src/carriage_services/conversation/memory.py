import datetime
from uuid import UUID

from loguru import logger
from sqlalchemy.orm import Session

from carriage_services.database import Conversation, create_log_entry
from carriage_services.utils import ConversationStatus, LeadStatus, LogMessageSource
from carriage_services.utils.anonymization import anonymize_text


class MemoryService:
    """Stores and loads information about conversation."""

    def __init__(self, db: Session):
        """
        Initializes the MemoryService.

        Args:
            db: The database session.
        """
        self.db = db

    def store_conversation(self, to_number: str, user_id: str | None, handoff_number: str | None) -> Conversation:
        """
        Creates a conversation record.

        Args:
            to_number: The destination phone number.
            user_id: An optional user identifier.
            handoff_number: An optional number for call transfer.

        Returns:
            A Conversation object representing the created conversation.
        """
        logger.info(f"Storing information about the call to number {to_number} for user '{user_id}'")

        conversation = Conversation(
            to_number=to_number,
            user_id=user_id,
            handoff_number=handoff_number,
            status=ConversationStatus.PENDING,
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def update_conversation(self, conversation_id: UUID, call_sid: str) -> None:
        """Updates information about the conversation in database.

        Args:
            conversation_id: The ID of the conversation to store info about.
            call_sid: The SID of the call.
        """
        conversation = self.db.query(Conversation).filter(Conversation.id == conversation_id).first()

        try:
            conversation.status = ConversationStatus.CALLING
            conversation.call_sid = call_sid
            conversation.updated_at = datetime.datetime.now(datetime.UTC)  # type: ignore
            self.db.commit()

        except Exception as e:
            logger.error(f"Failed to initiate call for Conversation ID {conversation.id}: {e}")
            conversation.status = ConversationStatus.ERROR
            conversation.updated_at = datetime.datetime.now(datetime.UTC)  # type: ignore
            self.db.commit()

    async def store_bot_message(self, conversation_id: UUID, message: str) -> None:
        """
        Stores a message sent by the bot in the conversation log.

        Args:
            conversation_id: The ID of the conversation.
            message: The message to be logged.
        """
        anonymized_message = await anonymize_text(message)
        create_log_entry(
            self.db,
            conversation_id=conversation_id,
            message=anonymized_message,
            source=LogMessageSource.BOT,
        )

    async def store_user_message(
        self,
        conversation_id: UUID,
        transcription: str,
        confidence: float,
        status: ConversationStatus | None = None,
        lead_status: LeadStatus | None = None,
    ) -> None:
        """
        Processes the speech-to-text result and updates the conversation status.

        Args:
            conversation_id: The ID of the conversation.
            transcription: The transcribed text from the user.
            confidence: The confidence score of the transcription.
            status: The conversation status to update with.
            lead_status: The lead status to update with (optional).
        """
        anonymized_transcription = await anonymize_text(transcription)
        saved_transcription = f"{anonymized_transcription} (confidence: {confidence:.2f})"
        create_log_entry(
            db=self.db, conversation_id=conversation_id, message=saved_transcription, source=LogMessageSource.USER
        )

        conversation = self.db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if conversation:
            if status is not None:
                conversation.status = status
            if lead_status is not None:
                conversation.lead_status = lead_status
            conversation.updated_at = datetime.datetime.now(datetime.UTC)  # type: ignore
            self.db.commit()
