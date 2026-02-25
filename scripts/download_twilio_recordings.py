import sys

import click
from loguru import logger

from carriage_services.utils.twilio_downloader import TwilioRecordingDownloader


@click.command()
@click.option("--outbound-number", help="Download recordings for all calls from this phone number (E.164 format)")
@click.option("--call-sid", help="Download recordings for a specific call SID")
def download_recordings(outbound_number: str, call_sid: str) -> None:
    """
    Download Twilio recordings by outbound number or call SID.
    Provide either --outbound-number OR --call-sid (not both).
    Recordings will be saved to: data/call_recordings/{number}/
    """
    if not outbound_number and not call_sid:
        logger.error("Error: Must provide either --outbound-number or --call-sid")
        sys.exit(1)

    if outbound_number and call_sid:
        logger.error("Error: Cannot provide both --outbound-number and --call-sid. Choose one.")
        sys.exit(1)

    downloader = TwilioRecordingDownloader()

    try:
        if outbound_number:
            successful_downloads = downloader.download_all_recordings_for_number(outbound_number)
            operation_description = f"for outbound number {outbound_number}"
        else:
            successful_downloads = downloader.download_recordings_for_call_sid(call_sid)
            operation_description = f"for call SID {call_sid}"

        if successful_downloads > 0:
            logger.info(f"Successfully downloaded {successful_downloads} recordings {operation_description}!")
        else:
            logger.warning(f"No recordings were downloaded {operation_description}.")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    download_recordings()
