#!/usr/bin/env python3
"""
An independent latency testing tool for Dynamics 365 vendor APIs.

This script measures the response time for the two-step process of finding available slots:
1. Fetching lead details to dynamically discover the lead's owner (the calendar_id).
2. Fetching available calendar slots using the dynamically obtained calendar_id.

It can run in two modes:
- Sequential: Makes API calls one after another.
- Concurrent: Makes API calls simultaneously to test load performance.

It requires a valid Lead GUID to run.
Ensure your .env file is populated with the correct DYNAMICS_* credentials.

Example Usage:
uv run ./scripts/latency_test_dynamics.py \
    --mode concurrent \
    --requests 20 \
    --lead-id "your-lead-guid"
"""

import asyncio
import statistics
import sys
import time
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import click
from loguru import logger

# Add the project root to the Python path to allow imports from the main application
sys.path.append(str(Path(__file__).resolve().parent.parent))

from carriage_services.calendar.provider import DynamicsCalendarProvider
from carriage_services.settings import settings


class DynamicsLatencyTester:
    """A tool to test the latency of Dynamics 365 API endpoints."""

    def __init__(self, lead_id: str, num_requests: int):
        """
        Initializes the latency tester.

        Args:
            lead_id: A valid Lead GUID from Dynamics.
            num_requests: The number of requests to perform for each endpoint.
        """
        if not settings.calendar.DYNAMICS_ERP_BOOKING or not settings.calendar.DYNAMICS_API_URL:
            logger.error("Dynamics 365 is not enabled or configured in the settings. Please check your .env file.")
            sys.exit(1)

        self.lead_id = lead_id
        self.num_requests = num_requests
        self.provider = DynamicsCalendarProvider()

        self.fetch_owner_latencies: list[float] = []
        self.available_slots_latencies: list[float] = []
        self.fetch_owner_failures = 0
        self.available_slots_failures = 0

    @staticmethod
    async def _time_call(coro_func: Callable[[], Awaitable]) -> tuple[float | None, Any]:
        """Wraps a coroutine to measure its execution time and return its result."""
        start_time = time.perf_counter()
        result = await coro_func()
        end_time = time.perf_counter()
        return end_time - start_time, result

    async def _test_fetch_owner_and_calendar_id(self) -> str | None:
        """Performs and times a single get_lead_details call to get the calendar_id."""
        try:
            latency, lead_details = await self._time_call(lambda: self.provider.get_lead_details(self.lead_id))
            if latency is not None:
                self.fetch_owner_latencies.append(latency)
                calendar_id = lead_details.get("calendar_id")
                if calendar_id:
                    logger.info(f"SUCCESS: Fetched owner/calendar_id in {latency:.4f}s")
                    return calendar_id
                else:
                    raise ValueError("calendar_id not found in lead details response.")
            return None
        except Exception as e:
            self.fetch_owner_failures += 1
            logger.error(f"FAILURE: Fetching owner/calendar_id failed: {e}")
            return None

    async def _test_get_available_slots(self, calendar_id: str | None) -> None:
        """Performs and times a single get_available_slots API call."""
        if not calendar_id:
            self.available_slots_failures += 1
            logger.error("SKIPPED: get_available_slots because calendar_id was not fetched.")
            return

        try:
            start_date = date.today() + timedelta(days=1)
            end_date = start_date + timedelta(days=settings.calendar.AVAILABILITY_LOOKAHEAD_DAYS)
            duration = settings.calendar.APPOINTMENT_DURATION_MINUTES

            latency, _ = await self._time_call(
                lambda: self.provider.get_available_slots(calendar_id, start_date, end_date, duration)
            )
            if latency is not None:
                self.available_slots_latencies.append(latency)
                logger.info(f"SUCCESS: get_available_slots took {latency:.4f}s")
        except Exception as e:
            self.available_slots_failures += 1
            logger.error(f"FAILURE: get_available_slots failed: {e}")

    async def run_sequential(self) -> None:
        """Runs latency tests sequentially."""
        logger.info(f"--- Starting Sequential Test ({self.num_requests} requests for each step) ---")
        for i in range(self.num_requests):
            logger.info(f"Request Set {i + 1}/{self.num_requests}...")
            calendar_id = await self._test_fetch_owner_and_calendar_id()
            await self._test_get_available_slots(calendar_id)
        logger.info("--- Sequential Test Finished ---")

    async def run_concurrent(self) -> None:
        """Runs latency tests concurrently in two stages."""
        logger.info(f"--- Starting Concurrent Test ({self.num_requests} requests for each step) ---")

        # Stage 1: Fetch all calendar_ids concurrently
        logger.info(f"Stage 1: Concurrently fetching {self.num_requests} calendar_ids...")
        fetch_tasks = [self._test_fetch_owner_and_calendar_id() for _ in range(self.num_requests)]
        fetched_calendar_ids = await asyncio.gather(*fetch_tasks)
        logger.info("Stage 1 Finished.")

        # Stage 2: Use the fetched calendar_ids to get available slots concurrently
        logger.info(
            f"Stage 2: Concurrently fetching available slots for {len(fetched_calendar_ids)} valid calendar_ids..."
        )
        slot_tasks = [self._test_get_available_slots(cid) for cid in fetched_calendar_ids]
        await asyncio.gather(*slot_tasks)
        logger.info("Stage 2 Finished.")

        logger.info("--- Concurrent Test Finished ---")

    @staticmethod
    def _print_stats_for_endpoint(name: str, latencies: list[float], failures: int) -> None:
        """Calculates and prints latency statistics for a given endpoint."""
        print(f"\n--- Stats for: {name} ---")

        total_requests = len(latencies) + failures
        print(f"Total Requests: {total_requests}")
        print(f"Successful:     {len(latencies)}")
        print(f"Failed:         {failures}")

        if not latencies:
            print("No successful requests to analyze.")
            return

        latencies.sort()

        mean = statistics.mean(latencies)
        median = statistics.median(latencies)
        p95_index = int(len(latencies) * 0.95)
        p95 = latencies[p95_index] if p95_index < len(latencies) else latencies[-1]

        print(f"Min Latency:    {min(latencies):.4f}s")
        print(f"Max Latency:    {max(latencies):.4f}s")
        print(f"Average Latency:{mean:.4f}s")
        print(f"Median Latency: {median:.4f}s")
        print(f"95th Percentile:{p95:.4f}s")

    def report_results(self) -> None:
        """Prints a summary report of the latency tests."""
        self._print_stats_for_endpoint(
            "1. Get Lead Details (to fetch Owner/Calendar ID)", self.fetch_owner_latencies, self.fetch_owner_failures
        )
        self._print_stats_for_endpoint(
            "2. Get Available Slots (using fetched Calendar ID)",
            self.available_slots_latencies,
            self.available_slots_failures,
        )
        print("\n--- Test Complete ---")


@click.command(help="An independent latency testing tool for Dynamics 365 vendor APIs.")
@click.option(
    "--mode",
    "-m",
    "mode",
    type=click.Choice(["s", "c", "sequential", "concurrent"], case_sensitive=False),
    default="s",
    help="Run in sequential (s) or concurrent (c) mode. Default: sequential.",
)
@click.option(
    "--requests",
    "-n",
    type=int,
    default=10,
    show_default=True,
    help="Number of requests to send for each endpoint.",
)
@click.option(
    "--lead-id",
    required=True,
    help="A valid Lead GUID from Dynamics to test the APIs.",
)
def main(mode: str, requests: int, lead_id: str) -> None:
    """Main function to run the latency test from the command line."""
    logger.remove()
    logger.add(sys.stderr, level="INFO")

    tester = DynamicsLatencyTester(lead_id=lead_id, num_requests=requests)

    run_mode = mode.lower()
    if run_mode.startswith("s"):
        asyncio.run(tester.run_sequential())
    else:
        asyncio.run(tester.run_concurrent())

    tester.report_results()


if __name__ == "__main__":
    main()
