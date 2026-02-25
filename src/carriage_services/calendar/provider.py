import asyncio
import time as time_module
from abc import ABC, abstractmethod
from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Any

import httpx
import msal
from loguru import logger

from carriage_services.calendar.models import BookingResult
from carriage_services.settings import settings


class SlotUnavailableError(Exception):
    """Custom exception for when a calendar slot is already booked or otherwise unavailable."""

    pass


class CalendarProvider(ABC):
    """Abstract base class for calendar providers."""

    @abstractmethod
    async def get_lead_details(self, lead_id: str) -> dict[str, Any]:
        """Fetches full details for a given lead, including name, email, and owner ID."""
        pass

    @abstractmethod
    async def get_available_slots(
        self, calendar_id: str, start_date: date, end_date: date, duration_minutes: int
    ) -> list[datetime]:
        """Get available time slots for a given calendar."""
        pass

    @abstractmethod
    async def book_slot(
        self,
        calendar_id: str,
        start_time: datetime,
        duration_minutes: int,
        subject: str,
        attendee_email: str | None = None,
    ) -> BookingResult:
        """Book a time slot in a given calendar."""
        pass

    @abstractmethod
    async def delete_event(self, event_id: str) -> bool:
        """Deletes an event from the calendar system."""
        pass


class DynamicsCalendarProvider(CalendarProvider):
    """Dynamics 365 Web API implementation of the calendar provider."""

    def __init__(self) -> None:
        self.calendar_settings = settings.calendar
        self.enabled = all(
            [
                self.calendar_settings.DYNAMICS_API_URL,
                self.calendar_settings.DYNAMICS_TENANT_ID,
                self.calendar_settings.DYNAMICS_CLIENT_ID,
                self.calendar_settings.DYNAMICS_CLIENT_SECRET,
                self.calendar_settings.DYNAMICS_API_VERSION,
            ]
        )

        if self.enabled:
            self.authority = f"https://login.microsoftonline.com/{self.calendar_settings.DYNAMICS_TENANT_ID}"
            self.scope = [f"{self.calendar_settings.DYNAMICS_API_URL}/.default"]
            self.client_app = msal.ConfidentialClientApplication(
                client_id=self.calendar_settings.DYNAMICS_CLIENT_ID,
                authority=self.authority,
                client_credential=self.calendar_settings.DYNAMICS_CLIENT_SECRET,
            )
            self._token_cache: dict[str, Any] = {}
            self.base_url = f"{self.calendar_settings.DYNAMICS_API_URL}{self.calendar_settings.DYNAMICS_API_VERSION}"
            # Initialize a reusable client with a longer timeout (30 seconds).
            self.http_client = httpx.AsyncClient(timeout=30.0)
            logger.info("Dynamics 365 Calendar provider initialized and enabled.")
        else:
            logger.warning("Dynamics 365 settings are not fully configured. Calendar provider is disabled.")

    async def _get_access_token(self) -> str:
        """Acquire or refresh an access token."""
        if self._token_cache and self._token_cache.get("expires_at", 0) > time_module.time() + 60:
            return self._token_cache["access_token"]

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, self.client_app.acquire_token_for_client, self.scope)

        if "access_token" not in result:
            logger.error(f"Failed to acquire token for Dynamics: {result.get('error_description')}")
            raise ConnectionError("Could not authenticate with Dynamics 365.")

        result["expires_at"] = time_module.time() + result.get("expires_in", 0)
        self._token_cache = result
        return result["access_token"]

    @staticmethod
    def _validate_and_format_guid(guid: str) -> str:
        """Validate and format a GUID for Dynamics 365 queries."""
        # Remove any surrounding quotes, braces, or extra characters
        guid = guid.strip().strip("'\"{}()")

        # Remove hyphens to get raw hex string
        guid_no_hyphens = guid.replace("-", "")

        # Validate GUID format (32 hex characters)
        if len(guid_no_hyphens) != 32:
            logger.error(f"Invalid GUID format: {guid} (length: {len(guid_no_hyphens)})")
            raise ValueError(f"Invalid GUID format: {guid}")

        try:
            # Validate hex characters
            int(guid_no_hyphens, 16)
        except ValueError as e:
            logger.error(f"GUID contains invalid characters: {guid}")
            raise ValueError(f"GUID contains invalid characters: {guid}") from e

        # Return in standard format with hyphens
        formatted_guid = (
            f"{guid_no_hyphens[:8]}-{guid_no_hyphens[8:12]}-"
            f"{guid_no_hyphens[12:16]}-{guid_no_hyphens[16:20]}-{guid_no_hyphens[20:32]}"
        )
        logger.debug(f"Formatted GUID from {guid} to {formatted_guid}")
        return formatted_guid

    async def get_lead_details(self, lead_id: str) -> dict[str, Any]:
        """Fetches full details for a given lead, including name, email, and owner ID."""
        if not self.enabled:
            raise ConnectionError("Dynamics 365 provider is not configured.")

        # Validate and format the lead_id GUID
        try:
            formatted_lead_id = self._validate_and_format_guid(lead_id)
            logger.debug(f"Using formatted lead_id: {formatted_lead_id}")
        except ValueError as e:
            logger.error(f"Invalid lead_id format: {e}")
            raise ValueError(f"Invalid lead_id format: {e}") from e

        token = await self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
        }
        query = "$select=fullname,emailaddress1,_ownerid_value"
        url = f"{self.base_url}/leads({formatted_lead_id})?{query}"

        logger.debug(f"Making Dynamics API request to: {url}")
        response = await self.http_client.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            owner_id = data.get("_ownerid_value")
            if not owner_id:
                raise ValueError(f"Lead with ID {lead_id} found, but it has no owner ID.")

            return {
                "lead_id": lead_id,
                "user_name": data.get("fullname"),
                "email": data.get("emailaddress1"),
                "calendar_id": owner_id,
                # Add other fields from your CRM as needed
                "phone": None,
                "interest_level": None,
                "source": "dynamics_crm",
                "funeral_home_name": "Bradshaw Carter Funeral Home",  # Placeholder
                "funeral_home_address": "123 Main St, Anytown, USA",  # Placeholder
            }

        logger.error(f"Dynamics API Error fetching lead details for {lead_id}: {response.status_code} {response.text}")
        if response.status_code == 404:
            raise FileNotFoundError(f"Lead with ID {lead_id} not found.")
        raise OSError("Failed to fetch lead details from Dynamics 365.")

    async def get_lead_owner_id(self, lead_id: str) -> str:
        """Fetches the GUID of the systemuser who owns the specified lead."""
        if not self.enabled:
            raise ConnectionError("Dynamics 365 provider is not configured.")

        token = await self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
        }
        url = f"{self.base_url}/leads({lead_id})?$select=_ownerid_value"

        response = await self.http_client.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            owner_id = data.get("_ownerid_value")
            if not owner_id:
                raise ValueError(f"Lead with ID {lead_id} found, but it has no owner ID.")
            return owner_id

        logger.error(
            f"Dynamics API Error fetching lead owner for lead {lead_id}: {response.status_code} {response.text}"
        )
        if response.status_code == 404:
            raise FileNotFoundError(f"Lead with ID {lead_id} not found.")
        raise OSError("Failed to fetch lead owner from Dynamics 365.")

    async def get_available_slots(
        self, calendar_id: str, start_date: date, end_date: date, duration_minutes: int
    ) -> list[datetime]:
        """Get available slots by checking existing appointments and calculating free time."""
        if not self.enabled:
            return []

        logger.info(f"Getting available slots for calendar_id: {calendar_id} from {start_date} to {end_date}")

        try:
            # First try Field Service API if available
            return await self._get_available_slots_field_service(calendar_id, start_date, end_date, duration_minutes)
        except Exception as e:
            logger.warning(f"Field Service API not available ({e}), falling back to appointment-based calculation")
            # Fallback to appointment-based calculation
            return await self._get_available_slots_from_appointments(
                calendar_id, start_date, end_date, duration_minutes
            )

    async def _get_available_slots_field_service(
        self, calendar_id: str, start_date: date, end_date: date, duration_minutes: int
    ) -> list[datetime]:
        """Try to get available slots using Field Service API."""
        token = await self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
            "Content-Type": "application/json",
        }

        start_datetime = datetime.combine(start_date, time.min, tzinfo=UTC)
        end_datetime = datetime.combine(end_date, time.max, tzinfo=UTC)

        payload = {
            "Version": "1",
            "Requirement": {
                "msdyn_fromdate": start_datetime.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "msdyn_todate": end_datetime.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "msdyn_remainingduration": duration_minutes,
                "msdyn_duration": duration_minutes,
            },
            "Settings": {
                "ConsiderSlotsWithProposedBookings": False,
                "ConsiderTravelTime": False,
            },
            "ResourceSpecification": {
                "ResourceIds": [calendar_id],
            },
        }

        url = f"{self.base_url}/msdyn_SearchResourceAvailability"
        response = await self.http_client.post(url, headers=headers, json=payload)

        if response.status_code != 200:
            raise Exception(f"Field Service API error: {response.status_code} {response.text}")

        data = response.json()
        time_slots = data.get("TimeSlots", [])

        return [
            datetime.fromisoformat(slot["StartTime"].replace("Z", "+00:00"))
            for slot in time_slots
            if "StartTime" in slot
        ]

    async def _get_available_slots_from_appointments(
        self, calendar_id: str, start_date: date, end_date: date, duration_minutes: int
    ) -> list[datetime]:
        """Calculate available slots by fetching existing appointments and finding gaps."""
        token = await self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
        }

        # Validate and format the calendar_id GUID
        try:
            formatted_calendar_id = self._validate_and_format_guid(calendar_id)
        except ValueError as e:
            logger.error(f"Invalid calendar_id format: {e}")
            return []

        # Format dates for OData query
        start_datetime = datetime.combine(start_date, time.min, tzinfo=UTC)
        end_datetime = datetime.combine(end_date, time.max, tzinfo=UTC)

        # Query appointments for the owner in the date range
        filter_query = (
            f"_ownerid_value eq {formatted_calendar_id} and "
            f"scheduledstart ge {start_datetime.strftime('%Y-%m-%dT%H:%M:%S.000Z')} and "
            f"scheduledend le {end_datetime.strftime('%Y-%m-%dT%H:%M:%S.000Z')}"
        )

        query = f"$select=scheduledstart,scheduledend&$filter={filter_query}"
        url = f"{self.base_url}/appointments?{query}"

        logger.debug(f"Fetching appointments with URL: {url}")
        response = await self.http_client.get(url, headers=headers)

        if response.status_code != 200:
            logger.error(f"Error fetching appointments: {response.status_code} {response.text}")
            return []

        appointments_data = response.json()
        appointments = appointments_data.get("value", [])

        # Convert to busy intervals
        busy_intervals = []
        for apt in appointments:
            if apt.get("scheduledstart") and apt.get("scheduledend"):
                start = datetime.fromisoformat(apt["scheduledstart"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(apt["scheduledend"].replace("Z", "+00:00"))
                busy_intervals.append((start, end))

        logger.info(f"Found {len(busy_intervals)} busy intervals for calendar_id {calendar_id}")

        # Calculate available slots from busy intervals
        return self._calculate_slots_from_busy_intervals(busy_intervals, start_date, end_date, duration_minutes, UTC)

    @staticmethod
    def _calculate_slots_from_busy_intervals(
        busy_intervals: list[tuple[datetime, datetime]],
        start_date: date,
        end_date: date,
        duration_minutes: int,
        tz: timezone,
    ) -> list[datetime]:
        """Calculates available slots from a list of busy intervals."""
        calendar_settings = settings.calendar
        working_hours_start = time.fromisoformat(calendar_settings.WORKING_HOURS_START)
        working_hours_end = time.fromisoformat(calendar_settings.WORKING_HOURS_END)
        working_days = {0, 1, 2, 3, 4}  # Monday to Friday
        slot_duration = timedelta(minutes=duration_minutes)
        available_slots = []

        sorted_busy = sorted(busy_intervals)

        current_day = start_date
        while current_day <= end_date:
            if current_day.weekday() not in working_days:
                current_day += timedelta(days=1)
                continue

            day_start = datetime.combine(current_day, working_hours_start, tzinfo=tz)
            day_end = datetime.combine(current_day, working_hours_end, tzinfo=tz)
            potential_slot_start = day_start
            day_busy_intervals = [b for b in sorted_busy if b[0].date() == current_day]

            for busy_start, busy_end in day_busy_intervals:
                while potential_slot_start + slot_duration <= busy_start:
                    if potential_slot_start < day_end:
                        available_slots.append(potential_slot_start)
                    potential_slot_start += slot_duration
                potential_slot_start = max(potential_slot_start, busy_end)

            while potential_slot_start + slot_duration <= day_end:
                available_slots.append(potential_slot_start)
                potential_slot_start += slot_duration

            current_day += timedelta(days=1)

        return available_slots

    async def book_slot(
        self,
        calendar_id: str,
        start_time: datetime,
        duration_minutes: int,
        subject: str,
        attendee_email: str | None = None,
    ) -> BookingResult:
        """Creates an appointment entity in Dynamics 365."""
        if not self.enabled:
            raise ConnectionError("Cannot book slot: Dynamics 365 provider is not configured.")

        token = await self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
            "Content-Type": "application/json",
        }

        end_time = start_time + timedelta(minutes=duration_minutes)

        appointment_data = {
            "subject": subject,
            "scheduledstart": start_time.isoformat(),
            "scheduledend": end_time.isoformat(),
            "ownerid@odata.bind": f"/systemusers({calendar_id})",
        }

        url = f"{self.base_url}/appointments"

        response = await self.http_client.post(url, headers=headers, json=appointment_data)

        if response.status_code == 204:
            entity_id_url = response.headers.get("OData-EntityId")
            event_id = entity_id_url.split("(")[-1].split(")")[0]
            web_link = f"{self.calendar_settings.DYNAMICS_API_URL}/main.aspx?etn=appointment&id={event_id}&pagetype=entityrecord"  # noqa: E501
            return BookingResult(id=event_id, webLink=web_link)

        # Handle specific error for scheduling conflicts (e.g., 400 Bad Request with specific error message)
        if response.status_code == 400:
            logger.warning(f"Potential slot conflict booking appointment: {response.status_code} {response.text}")
            raise SlotUnavailableError("The requested time slot is no longer available.")

        logger.error(f"Dynamics API Error creating appointment: {response.status_code} {response.text}")
        raise OSError("Failed to book appointment via Dynamics 365.")

    async def delete_event(self, event_id: str) -> bool:
        """Deletes an appointment from Dynamics 365."""
        if not self.enabled:
            raise ConnectionError("Cannot delete event: Dynamics 365 provider is not configured.")

        token = await self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{self.base_url}/appointments({event_id})"

        response = await self.http_client.delete(url, headers=headers)

        if response.status_code == 204:
            logger.info(f"Successfully deleted Dynamics appointment {event_id}")
            return True

        logger.error(f"Dynamics API Error deleting appointment: {response.status_code} {response.text}")
        return False
