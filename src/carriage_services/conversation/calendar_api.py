"""Calendar API module for appointment booking functionality."""

from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any
from uuid import UUID

from loguru import logger

from carriage_services.calendar.provider import CalendarProvider, DynamicsCalendarProvider, SlotUnavailableError
from carriage_services.database import get_db
from carriage_services.database.actions import merge_conversation_context
from carriage_services.settings import settings


class _ProviderManager:
    """Manages the singleton instance of the CalendarProvider."""

    _instance: CalendarProvider | None = None

    @classmethod
    def get(cls) -> CalendarProvider:
        """Gets the singleton instance, creating it if it doesn't exist."""
        if cls._instance is None:
            cls._instance = DynamicsCalendarProvider()
        return cls._instance

    @classmethod
    def set(cls, provider: CalendarProvider | None) -> None:
        """Sets or resets the singleton instance."""
        cls._instance = provider

    @classmethod
    def get_fresh(cls) -> CalendarProvider:
        """Creates a fresh provider instance for background tasks."""
        return DynamicsCalendarProvider()


def set_calendar_provider(provider: CalendarProvider | None) -> None:
    """Injects a calendar provider instance for use by this module."""
    _ProviderManager.set(provider)


def get_calendar_provider() -> CalendarProvider:
    """
    Returns the configured calendar provider.
    Initializes the default Dynamics provider if none is set.
    """
    return _ProviderManager.get()


class BookingStatus(Enum):
    """Enumeration for the result of a booking attempt."""

    SUCCESS = "success"
    SLOT_UNAVAILABLE = "slot_unavailable"
    LEAD_INVALID = "lead_invalid"
    SYSTEM_ERROR = "system_error"
    UNEXPECTED_ERROR = "unexpected_error"


def mock_calendar_api_get_initial_date_slot() -> datetime:
    """Mock calendar API to get an initial available date slot."""
    return datetime(2025, 1, 15, 14, 0)


def mock_calendar_api_get_available_dates() -> list[datetime]:
    """Get available dates from calendar API."""
    return [
        datetime(2025, 1, 15, 14, 0),
        datetime(2025, 1, 16, 10, 0),
        datetime(2025, 1, 17, 10, 0),
        datetime(2025, 1, 17, 11, 0),
        datetime(2025, 1, 17, 15, 0),
        datetime(2025, 1, 18, 16, 0),
        datetime(2025, 1, 21, 9, 0),
        datetime(2025, 1, 22, 13, 0),
        datetime(2025, 1, 23, 11, 0),
        datetime(2025, 1, 23, 16, 0),
    ]


def mock_send_to_booking_api(selected_datetime: datetime) -> None:
    """Mock sending selected datetime to booking API."""
    logger.info(f"Mock booking API called with data: {selected_datetime}")


def get_initial_date_slot(available_dates: list[datetime]) -> datetime | None:
    """
    Get an initial available date slot from a list of available dates.
    """
    return available_dates[0] if available_dates else None


async def get_lead_details(lead_id: str) -> dict[str, Any] | None:
    """
    Get lead details from the CRM.
    """
    provider = get_calendar_provider()
    if not getattr(provider, "enabled", True):
        logger.warning("Dynamics provider not configured, cannot get lead details.")
        return None

    try:
        return await provider.get_lead_details(lead_id=lead_id)
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Invalid lead data for lead_id {lead_id}. Cannot retrieve details: {e}")
        return None
    except (ConnectionError, OSError) as e:
        logger.error(f"System or network error retrieving details for lead {lead_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred while getting lead details for lead {lead_id}: {e}")
        return None


async def get_available_dates(calendar_id: str, lead_id: str) -> list[datetime]:
    """
    Get available dates from the calendar of the owner of the specified lead.
    """
    provider = get_calendar_provider()
    if not getattr(provider, "enabled", True):
        logger.warning("Dynamics provider not configured, returning no dates.")
        return []

    try:
        # Fetch available slots for that specific owner.
        start_date = date.today() + timedelta(days=1)  # Start from tomorrow
        end_date = start_date + timedelta(days=settings.calendar.AVAILABILITY_LOOKAHEAD_DAYS)
        return await provider.get_available_slots(
            calendar_id=calendar_id,
            start_date=start_date,
            end_date=end_date,
            duration_minutes=settings.calendar.APPOINTMENT_DURATION_MINUTES,
        )
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Invalid lead data for lead_id {lead_id}. Cannot retrieve calendar: {e}")
        return []
    except (ConnectionError, OSError) as e:
        logger.error(f"System or network error retrieving calendar for lead {lead_id}: {e}")
        return []
    except Exception as e:
        logger.error(f"An unexpected error occurred while getting available dates for lead {lead_id}: {e}")
        return []


async def book_appointment(
    selected_datetime: datetime,
    lead_info: dict,
    calendar_id: str,
    use_fresh_provider: bool = False,
    conversation_id: UUID | None = None,
) -> BookingStatus:
    """
    Book an appointment for the owner of the lead specified in lead_info.

    Args:
        selected_datetime: The datetime to book
        lead_info: Lead information dictionary
        calendar_id: The calendar ID to book on
        use_fresh_provider: If True, creates a fresh provider instance to avoid connection issues
        conversation_id: The ID of the conversation
    """
    provider = _ProviderManager.get_fresh() if use_fresh_provider else get_calendar_provider()

    try:
        if not getattr(provider, "enabled", True):
            logger.error("Cannot book appointment, Dynamics provider not configured.")
            return BookingStatus.SYSTEM_ERROR

        lead_id = lead_info.get("lead_id")
        if not lead_id:
            logger.error("Cannot book appointment, 'lead_id' is missing from lead_info.")
            return BookingStatus.LEAD_INVALID

        for i in range(3):
            try:
                logger.info(f"Booking for lead {lead_id} on owner's calendar {calendar_id}. Trial: {i+1}/3")
                subject = f"Appointment with {lead_info.get('user_name', 'New Client')}"
                await provider.book_slot(
                    calendar_id=calendar_id,
                    start_time=selected_datetime,
                    duration_minutes=settings.calendar.APPOINTMENT_DURATION_MINUTES,
                    subject=subject,
                    attendee_email=lead_info.get("email"),
                )
                logger.info(f"Booking API called successfully for owner {calendar_id} at {selected_datetime}")
                return BookingStatus.SUCCESS
            except SlotUnavailableError as e:
                logger.warning(f"Attempted to book an unavailable slot for lead {lead_id}: {e}")
                status = BookingStatus.SLOT_UNAVAILABLE
            except (FileNotFoundError, ValueError) as e:
                status = BookingStatus.LEAD_INVALID
                logger.error(f"Data integrity issue while booking for lead {lead_id}: {e}")
            except (ConnectionError, OSError) as e:
                status = BookingStatus.SYSTEM_ERROR
                logger.error(f"System error while booking appointment for lead {lead_id}: {e}")
            except Exception as e:
                status = BookingStatus.UNEXPECTED_ERROR
                logger.error(f"Unexpected error while booking appointment for lead {lead_id}: {e}")

        logger.warning(f"All booking attempts failed for lead {lead_id}.")
        _handle_unsuccessful_booking(selected_datetime, lead_info, conversation_id)
        return status

    finally:
        # Clean up fresh provider if used
        if use_fresh_provider and hasattr(provider, "http_client"):
            try:
                await provider.http_client.aclose()
            except Exception as e:
                logger.warning(f"Error closing HTTP client: {e}")


def _handle_unsuccessful_booking(selected_datetime: datetime, lead_info: dict, conversation_id: UUID | None) -> None:
    """Save unsuccessful booking attempt to conversation context."""
    try:
        with next(get_db()) as db:
            if conversation_id:
                unsuccessful_booking_data = {
                    "unsuccessful_booking": {
                        "lead_id": lead_info.get("lead_id"),
                        "requested_datetime": selected_datetime.isoformat(),
                        "lead_info": lead_info,
                        "failure_reason": "All booking attempts failed after multiple retries",
                        "timestamp": datetime.now().isoformat(),
                    }
                }
                merge_conversation_context(db, conversation_id, unsuccessful_booking_data)
    except Exception as db_error:
        logger.error(f"Failed to save unsuccessful booking to database: {db_error}")
