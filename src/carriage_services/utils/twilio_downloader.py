from pathlib import Path
from typing import Any

import requests
from loguru import logger
from twilio.rest import Client

from carriage_services.paths import CALL_RECORDINGS_PATH
from carriage_services.settings import settings


class TwilioRecordingDownloader:
    """Downloads recordings from Twilio for a specified outbound number or call SID."""

    def __init__(self) -> None:
        """Initialize the Twilio client with credentials from settings."""
        self.client = Client(settings.telephony.TWILIO_ACCOUNT_SID, settings.telephony.TWILIO_AUTH_TOKEN)
        self.account_sid = settings.telephony.TWILIO_ACCOUNT_SID
        self.auth_token = settings.telephony.TWILIO_AUTH_TOKEN

    def download_all_recordings_for_number(self, outbound_number: str) -> int:
        """
        Download all recordings for calls made from the specified outbound number.

        Args:
            outbound_number: The outbound phone number to filter recordings for

        Returns:
            Number of successfully downloaded recordings
        """
        sanitized_number = outbound_number.replace("+", "")
        output_dir = CALL_RECORDINGS_PATH / sanitized_number
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Fetching recordings for outbound number: {outbound_number}")

        calls = self.client.calls.list(to=outbound_number)
        call_sids = [call.sid for call in calls]
        logger.info(f"Found {len(call_sids)} calls from {outbound_number}")

        if not call_sids:
            logger.warning("No calls found for the specified outbound number")
            return 0

        all_recordings = []
        for call_sid in call_sids:
            try:
                recordings = self.client.recordings.list(call_sid=call_sid)
                all_recordings.extend(recordings)
                logger.debug(f"Found {len(recordings)} recordings for call {call_sid}")
            except Exception as e:
                logger.error(f"Error fetching recordings for call {call_sid}: {e}")

        logger.info(f"Total recordings found: {len(all_recordings)}")

        if not all_recordings:
            logger.warning("No recordings found to download")
            return 0

        return self._download_recordings(all_recordings, output_dir)

    def download_recordings_for_call_sid(self, call_sid: str, output_dir: Path | None = None) -> int:
        """
        Download all recordings for a specific call SID.

        Args:
            call_sid: The call SID to download recordings for
            output_dir: Optional directory to save recordings to. If not provided,
                defaults to data/call_recordings/{to_number}/ as per project paths.

        Returns:
            Number of successfully downloaded recordings
        """
        logger.info(f"Fetching recordings for call SID: {call_sid}")

        try:
            call = self.client.calls(call_sid).fetch()
            target_output_dir = output_dir
            if target_output_dir is None:
                sanitized_number = call.to.replace("+", "") if call.to else "unknown_number"
                target_output_dir = CALL_RECORDINGS_PATH / sanitized_number
            target_output_dir.mkdir(parents=True, exist_ok=True)

            recordings = self.client.recordings.list(call_sid=call_sid)
            logger.info(f"Found {len(recordings)} recordings for call {call_sid}")

            if not recordings:
                logger.warning("No recordings found for the specified call SID")
                return 0

            return self._download_recordings(recordings, target_output_dir)

        except Exception as e:
            logger.error(f"Error fetching call or recordings for {call_sid}: {e}")
            return 0

    def _download_recordings(self, recordings: list, output_dir: Path) -> int:
        """
        Download a list of recordings to the specified directory.

        Args:
            recordings: List of Twilio recording objects
            output_dir: Directory to save recordings to

        Returns:
            Number of successfully downloaded recordings
        """
        successful_downloads = 0
        for recording in recordings:
            try:
                date_created = (
                    recording.date_created.strftime("%Y%m%d_%H%M%S") if recording.date_created else "unknown_date"
                )
                filename = f"{date_created}_{recording.call_sid}_{recording.sid}.wav"

                media_url = (
                    f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Recordings/{recording.sid}.wav"
                )
                response = requests.get(media_url, auth=(self.account_sid, self.auth_token), timeout=30)
                response.raise_for_status()

                file_path = output_dir / filename
                with open(file_path, "wb") as f:
                    f.write(response.content)

                logger.info(f"Downloaded: {filename}")
                successful_downloads += 1

            except Exception as e:
                logger.error(f"Error downloading recording {recording.sid}: {e}")

        logger.info(f"Successfully downloaded {successful_downloads}/{len(recordings)} recordings to {output_dir}")
        return successful_downloads

    def get_recordings_data_for_call_sid(self, call_sid: str) -> dict[str, Any] | None:
        """
        Get recording data in memory for a specific call SID without saving to disk.
        Assumes only one recording per call SID.

        Args:
            call_sid: The call SID to get recording for

        Returns:
            Dictionary containing recording data, or None if no recording found
        """
        logger.info(f"Fetching recording data for call SID: {call_sid}")

        try:
            recordings = self.client.recordings.list(call_sid=call_sid)
            logger.info(f"Found {len(recordings)} recordings for call {call_sid}")

            if not recordings:
                logger.warning("No recordings found for the specified call SID")
                return None

            recording = recordings[0]

            try:
                filename = f"{recording.call_sid}.wav"

                media_url = (
                    f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Recordings/{recording.sid}.wav"
                )
                response = requests.get(media_url, auth=(self.account_sid, self.auth_token), timeout=30)
                response.raise_for_status()

                recording_data = {
                    "filename": filename,
                    "content": response.content,
                }

                logger.info(f"Successfully fetched recording data: {filename}")
                return recording_data

            except Exception as e:
                logger.error(f"Error fetching recording {recording.sid}: {e}")
                return None

        except Exception as e:
            logger.error(f"Error fetching recordings for {call_sid}: {e}")
            return None
