import logging
import os
import sys
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from carriage_services.calendar.models import BookingResult
from carriage_services.calendar.provider import CalendarProvider
from carriage_services.conversation import calendar_api
from carriage_services.database.models import Base
from carriage_services.paths import (
    INTENT_CLASSIFICATION_FAQS_PATH,
    INTENT_CLASSIFICATION_OBJECTIONS_PATH,
    SLOTS_WITH_RESPONSES_PATH,
)


class MockCalendarProvider(CalendarProvider):
    """A mock implementation of the CalendarProvider for testing."""

    @staticmethod
    async def get_lead_details(lead_id: str) -> dict[str, Any]:
        return {
            "lead_id": lead_id,
            "user_name": "Mocked User",
            "email": "mock@example.com",
            "calendar_id": "mock_calendar_id",
            "phone": "+15555555555",
            "interest_level": "high",
            "source": "mock_crm",
            "funeral_home_name": "Mock Funeral Home",
            "funeral_home_address": "123 Mock St, Mocksville, USA",
        }

    @staticmethod
    async def get_available_slots(
        calendar_id: str, start_date: date, end_date: date, duration_minutes: int
    ) -> list[datetime]:
        return [
            datetime(2025, 1, 15, 14, 0),
            datetime(2025, 1, 16, 10, 0),
        ]

    @staticmethod
    async def book_slot(
        calendar_id: str,
        start_time: datetime,
        duration_minutes: int,
        subject: str,
        attendee_email: str | None = None,
    ) -> BookingResult:
        return BookingResult(id="mock_event_id", webLink="http://mock.link/event")

    @staticmethod
    async def delete_event(event_id: str) -> bool:
        return True


@pytest.fixture(autouse=True)
def _inject_mock_calendar_provider() -> Generator[None, None, None]:
    """Injects the mock calendar provider for all tests."""
    mock_provider = MockCalendarProvider()
    calendar_api.set_calendar_provider(mock_provider)
    yield
    calendar_api.set_calendar_provider(None)


@pytest.fixture(autouse=True, scope="session")
def _setup_loguru_logging() -> None:
    logger.remove()
    logger.add(sys.stderr, level="INFO")

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)


@pytest.fixture()
def test_db_session() -> Generator[Session, None, None]:
    """
    Pytest fixture that provides a test database session.
    The database is automatically created and cleaned up.

    Returns:
        Session: A SQLAlchemy session bound to a temporary test database.
    """
    with test_database_session() as session:
        yield session


@contextmanager
def test_database_session():
    """
    Context manager that creates a temporary test database and returns a session.
    The database is automatically cleaned up when the context exits.
    """
    temp_db_fd, temp_db_path = tempfile.mkstemp(suffix=".db")
    temp_db_url = f"sqlite+pysqlite:///{temp_db_path}"

    try:
        test_engine = create_engine(temp_db_url, connect_args={"check_same_thread": False})
        TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

        Base.metadata.create_all(bind=test_engine)

        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()
            test_engine.dispose()
    finally:
        os.close(temp_db_fd)
        if Path(temp_db_path).exists():
            Path(temp_db_path).unlink()


@pytest.fixture()
def utterances() -> Generator[pd.DataFrame, None, None]:
    """
    Fixture that provides a set of utterances for testing.
    This can be extended with more utterances as needed.
    """
    utterances = pd.read_csv(SLOTS_WITH_RESPONSES_PATH)
    return utterances


@pytest.fixture()
def objection_utterances() -> Generator[pd.DataFrame, None, None]:
    """
    Fixture that provides a set of objection utterances for testing.
    This can be extended with more utterances as needed.
    """
    utterances = pd.read_csv(INTENT_CLASSIFICATION_OBJECTIONS_PATH)
    return utterances


@pytest.fixture()
def question_utterances() -> Generator[pd.DataFrame, None, None]:
    """
    Fixture that provides a set of question utterances for testing.
    This can be extended with more utterances as needed.
    """
    utterances = pd.read_csv(INTENT_CLASSIFICATION_FAQS_PATH)
    return utterances
