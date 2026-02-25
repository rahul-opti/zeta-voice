from enum import Enum


class LogMessageSource(str, Enum):
    """Enumeration for the source of a log message."""

    BOT = "bot"
    USER = "user"


class ConversationStatus(str, Enum):
    """Enumeration for the status of a conversation.
    Any value shouldn't be longer than 14 characters.
    """

    PENDING = "pending"
    CALLING = "calling"
    ANSWERED = "answered"
    COMPLETED = "completed"
    ERROR = "error"
    RESIGNED = "resigned"
    VOICEMAIL = "voicemail"
    WRONG_IDENTITY = "wrong_identity"
    START_BOOKING = "start_booking"
    REBUTTAL = "rebuttal"
    DO_NOT_CALL = "do_not_call"


class LeadStatus(str, Enum):
    """Enumeration for the final outcome status of a lead."""

    UNKNOWN = "unknown"
    BOOKED = "booked"
    TRANSFERRED = "transferred"
    ATTEND_SEMINAR = "attend_seminar"
    REJECTED = "rejected"
    DATE_SELECTED = "date_selected"


class BookingFlowPersona(str, Enum):
    """Enumeration for the persona of the booking flow bot."""

    EMPATHETIC_AND_PROFESSIONAL = "empathetic_and_professional"
    DIRECT_AND_EFFICIENT = "direct_and_efficient"
    GENTLE_AND_PATIENT = "gentle_and_patient"
