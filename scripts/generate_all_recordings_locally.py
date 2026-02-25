import subprocess
import sys
from dataclasses import dataclass

import click
from loguru import logger

from carriage_services.tts.tts import get_available_voice_names


@dataclass
class RecordingConfig:
    """Configuration for generating chatbot response recordings."""

    responses_file_path: str
    intent_name_column: str
    intent_response_columns: str
    description: str


def run_recording_generation(
    config: RecordingConfig,
    voice_name: str,
    remove_silence: bool = True,
    save_recordings_to: str = "data/recordings",
    *,
    skip_fillers: bool = False,
    only_fillers: bool = False,
) -> bool:
    """Run the save_chatbot_response_recordings_locally script with given config."""
    cmd = [
        "uv",
        "run",
        "./scripts/save_chatbot_response_recordings_locally.py",
        config.responses_file_path,
        config.intent_name_column,
        config.intent_response_columns,
        voice_name,
        "--save-recordings-to",
        save_recordings_to,
    ]

    if remove_silence:
        cmd.append("--remove-silence")
    else:
        cmd.append("--no-remove-silence")

    if skip_fillers:
        cmd.append("--skip-fillers")
    if only_fillers:
        cmd.append("--only-fillers")

    logger.info(f"Generating {config.description} for {voice_name} voice (local)")
    logger.debug(f"Command: {' '.join(cmd)}")

    try:
        subprocess.run(cmd, check=True)  # noqa: S603  # Safe: using controlled command components
        logger.success(f"✓ Completed {config.description} for {voice_name}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"✗ Failed {config.description} for {voice_name}: {e}")
        return False


@click.command()
@click.option(
    "--remove-silence/--no-remove-silence",
    default=True,
    help="Whether to remove silence from audio recordings. Defaults to True.",
)
@click.option(
    "--save-recordings-to",
    default="data/local_recordings",
    help="Base directory to save recordings locally. Defaults to data/local_recordings.",
)
@click.option(
    "--skip-fillers",
    is_flag=True,
    default=False,
    help="Skip generation of filler_word_* columns.",
)
@click.option(
    "--only-fillers",
    is_flag=True,
    default=False,
    help="Generate only filler_word_* columns.",
)
@click.option(
    "--voice-name",
    default=None,
    help="Generate recordings for a specific voice only (e.g., 'Luke'). If not provided, generates for all voices.",
)
def main(
    remove_silence: bool, save_recordings_to: str, skip_fillers: bool, only_fillers: bool, voice_name: str | None
) -> None:
    """Generate all chatbot response recordings locally for all configured voices."""
    if skip_fillers and only_fillers:
        logger.error("--skip-fillers and --only-fillers cannot be used together.")
        sys.exit(2)

    configs = [
        RecordingConfig(
            responses_file_path="config/conversation_config/slots_with_responses.csv",
            intent_name_column="slot_name",
            intent_response_columns="filler_word_1,filler_word_2,filler_word_3,filler_word_4,filler_word_5,intro_chatbot_response,example_chatbot_response_1,example_chatbot_response_2,example_chatbot_response_3,example_chatbot_response_4,example_chatbot_response_5",
            description="slots with responses",
        ),
        RecordingConfig(
            responses_file_path="config/conversation_config/faqs_with_responses.csv",
            intent_name_column="name_id",
            intent_response_columns="example_chatbot_response_1,example_chatbot_response_2,example_chatbot_response_3,example_chatbot_response_4,example_chatbot_response_5",
            description="FAQs with responses",
        ),
        RecordingConfig(
            responses_file_path="config/conversation_config/objections_with_responses.csv",
            intent_name_column="name_id",
            intent_response_columns="example_chatbot_response_1",
            description="objections with responses",
        ),
        RecordingConfig(
            responses_file_path="config/conversation_config/repetition_with_responses.csv",
            intent_name_column="name_id",
            intent_response_columns="example_chatbot_response_1",
            description="repetition with responses",
        ),
    ]

    available_voices = get_available_voice_names()

    if voice_name:
        if voice_name not in available_voices:
            logger.error(f"Voice '{voice_name}' not found. Available voices: {available_voices}")
            sys.exit(2)
        voice_names = [voice_name]
    else:
        voice_names = available_voices

    success_count = 0
    total_count = len(configs) * len(voice_names)

    logger.info(f"Starting generation of {total_count} recording sets for voices: {voice_names} (local)")

    for name in voice_names:
        logger.info(f"Processing {name} voice recordings")

        for config in configs:
            if run_recording_generation(
                config=config,
                voice_name=name,
                remove_silence=remove_silence,
                save_recordings_to=save_recordings_to,
                skip_fillers=skip_fillers,
                only_fillers=only_fillers,
            ):
                success_count += 1

    logger.info(f"Completed: {success_count}/{total_count} recording sets")

    if success_count == total_count:
        logger.success("All recordings generated successfully!")
        sys.exit(0)
    else:
        logger.error("Some recording generations failed. Check the logs above for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
