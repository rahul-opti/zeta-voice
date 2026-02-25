import datetime

from sqlalchemy import UUID, Column, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from carriage_services.utils import ConversationStatus, LeadStatus, LogMessageSource, default_uuid


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


class Conversation(Base):
    """Database model for a conversation entry."""

    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=default_uuid)
    user_id = Column(String, index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now(datetime.UTC), nullable=False)  # type: ignore

    to_number = Column(String, index=True, nullable=False)
    handoff_number = Column(String, nullable=True)
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus, name="conversation_status", native_enum=False),
        default=ConversationStatus.PENDING,
        nullable=False,
    )
    lead_status: Mapped[LeadStatus] = mapped_column(
        Enum(LeadStatus, name="lead_status", native_enum=False),
        default=LeadStatus.UNKNOWN,
    )

    call_sid = Column(String, nullable=True, unique=True)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.now(datetime.UTC),  # type: ignore
        onupdate=datetime.datetime.now(datetime.UTC),  # type: ignore
        nullable=False,
    )


class Log(Base):
    """Database model for a log entry, linked to a conversation."""

    __tablename__ = "logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=default_uuid)
    timestamp = Column(DateTime, default=datetime.datetime.now(datetime.UTC), nullable=False)  # type: ignore
    message = Column(Text, nullable=False)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False, index=True)
    source: Mapped[LogMessageSource] = mapped_column(
        Enum(LogMessageSource, name="log_message_source", native_enum=False),
        nullable=False,
        default=LogMessageSource.BOT,
    )


class Error(Base):
    """Database model for error entries, linked to a conversation."""

    __tablename__ = "errors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=default_uuid)
    timestamp = Column(DateTime, default=datetime.datetime.now(datetime.UTC), nullable=False)  # type: ignore
    error_message = Column(Text, nullable=False)
    function_name = Column(String, nullable=False)
    exception_type = Column(String, nullable=False)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False)
    stack_trace = Column(Text, nullable=False)


class ConversationContext(Base):
    """Database model for storing the full JSON context of a conversation."""

    __tablename__ = "conversation_contexts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=default_uuid)
    conversation_id = Column(
        UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False, index=True, unique=True
    )
    context_data = Column(Text, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.now(datetime.UTC),  # type: ignore
        onupdate=datetime.datetime.now(datetime.UTC),  # type: ignore
        nullable=False,
    )
