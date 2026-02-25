from datetime import datetime

from carriage_services.conversation.flows import BookingFlow
from carriage_services.utils.enums import LeadStatus


def test_booking_flow_lead_status_date_selected() -> None:
    """Test that BookingFlow returns DATE_SELECTED when selected_datetime is set but not booked."""
    booking_flow = BookingFlow()
    booking_flow.selected_datetime = datetime(2025, 1, 15, 14, 0)
    booking_flow.booking_made = False

    result = booking_flow.get_lead_status()

    assert result == LeadStatus.DATE_SELECTED


def test_booking_flow_lead_status_booked_when_booking_made() -> None:
    """Test that BookingFlow returns BOOKED when booking is made."""
    booking_flow = BookingFlow()
    booking_flow.selected_datetime = datetime(2025, 1, 15, 14, 0)
    booking_flow.booking_made = True

    result = booking_flow.get_lead_status()

    assert result == LeadStatus.BOOKED


def test_booking_flow_lead_status_unknown_when_no_datetime() -> None:
    """Test that BookingFlow returns UNKNOWN when no datetime is selected."""
    booking_flow = BookingFlow()
    booking_flow.selected_datetime = None
    booking_flow.booking_made = False

    result = booking_flow.get_lead_status()

    assert result == LeadStatus.UNKNOWN


def test_booking_flow_lead_status_precedence_booked_over_selected() -> None:
    """Test that BOOKED status takes precedence over DATE_SELECTED when both conditions are met."""
    booking_flow = BookingFlow()
    booking_flow.selected_datetime = datetime(2025, 1, 15, 14, 0)
    booking_flow.booking_made = True

    result = booking_flow.get_lead_status()

    assert result == LeadStatus.BOOKED
