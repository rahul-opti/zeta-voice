from datetime import datetime, time
from typing import Any

from pydantic import BaseModel, Field


class DateTimeTimeZone(BaseModel):
    """Represents a date, time, and time zone for an event."""

    date_time: datetime = Field(..., alias="dateTime")
    time_zone: str = Field(..., alias="timeZone")


class ScheduleItem(BaseModel):
    """Represents a single scheduled item in a calendar."""

    status: str
    start: DateTimeTimeZone
    end: DateTimeTimeZone


class WorkingHours(BaseModel):
    """Represents the working hours of a user or resource."""

    days_of_week: list[str] = Field(..., alias="daysOfWeek")
    start_time: time = Field(..., alias="startTime")
    end_time: time = Field(..., alias="endTime")
    time_zone: dict[str, Any] | None = Field(..., alias="timeZone")


class ScheduleInformation(BaseModel):
    """Represents the availability information for a single entity."""

    schedule_id: str = Field(..., alias="scheduleId")
    schedule_items: list[ScheduleItem] = Field(..., alias="scheduleItems")
    working_hours: WorkingHours = Field(..., alias="workingHours")


class Attendee(BaseModel):
    """Represents an attendee of an event."""

    email_address: dict[str, str] = Field(..., alias="emailAddress")
    type: str


class EventBody(BaseModel):
    """Represents the body of an event."""

    content_type: str = Field("HTML", alias="contentType")
    content: str


class Event(BaseModel):
    """Represents an event to be created in a calendar."""

    subject: str
    body: EventBody
    start: DateTimeTimeZone
    end: DateTimeTimeZone
    attendees: list[Attendee] = []


class BookingResult(BaseModel):
    """Represents the result of a successful booking operation."""

    id: str
    web_link: str = Field(..., alias="webLink")
