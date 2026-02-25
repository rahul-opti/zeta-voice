#!/usr/bin/env python3

import asyncio
from pathlib import Path

import click
import pandas as pd
from tqdm import tqdm

from carriage_services.audio.silence_remover import SilenceRemover
from carriage_services.settings import (
    ElevenLabsTTSSettings,
    settings,
)
from carriage_services.tts.elevenlabs_tts import (
    async_generate_speech as elevenlabs_async_generate_speech,
)
from carriage_services.tts.openai_tts import (
    async_generate_speech as openai_async_generate_speech,
)
from carriage_services.tts.tts import get_available_voice_names, get_voice_config


def _get_container_name() -> str:
    """Get the container name used in cloud to mirror locally."""
    if isinstance(settings.tts, ElevenLabsTTSSettings):
        return settings.storage.AZURE_STORAGE_STATIC_CONTAINER_NAME_11LABS
    return settings.storage.AZURE_STORAGE_STATIC_CONTAINER_NAME_OAI


def _build_output_path(
    base_path: Path, container_name: str, voice_id: str, intent_name: str, utterance_name: str
) -> Path:
    """Create output path mirroring cloud."""
    return base_path / container_name / voice_id / intent_name / f"{utterance_name}.mp3"


async def _generate_audio_bytes(text: str, voice_id: str, utterance_name: str, voice_name: str) -> bytes:
    """Generate audio bytes using given TTS provider."""
    config_name = f"{voice_name}_fillers" if "filler_word" in utterance_name else voice_name
    if isinstance(settings.tts, ElevenLabsTTSSettings):
        return await elevenlabs_async_generate_speech(text, settings.tts.TTS_MODEL, voice_id, config_name)
    return await openai_async_generate_speech(text, settings.tts.TTS_MODEL, voice_id)


async def process_responses_async(
    chatbot_responses: pd.DataFrame,
    intent_response_column: str,
    intent_name_column: str,
    voice_id: str,
    voice_name: str,
    remove_silence: bool,
    save_base_path: Path,
    max_concurrent: int = 30,
) -> None:
    """Process all responses asynchronously with limited concurrency and save locally."""
    semaphore = asyncio.Semaphore(max_concurrent)

    container_name = _get_container_name()
    silence_remover = SilenceRemover()

    async def process_single_response(row: pd.Series) -> None:
        text = row[intent_response_column]
        intent_name = str(row[intent_name_column])
        utterance_name = intent_response_column
        output_path = _build_output_path(save_base_path, container_name, voice_id, intent_name, utterance_name)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        async with semaphore:
            audio_bytes = await _generate_audio_bytes(text, voice_id, utterance_name, voice_name)
            if remove_silence:
                audio_bytes = silence_remover.remove_silence_from_bytes(audio_bytes, original_format="mp3")
            output_path.write_bytes(audio_bytes)

    tasks = []
    for _, row in chatbot_responses.iterrows():
        if not pd.isna(row[intent_response_column]):
            tasks.append(process_single_response(row))

    await asyncio.gather(*tasks)


@click.command()
@click.argument("responses-file-path", required=True)
@click.argument("intent-name-column", required=True)
@click.argument("intent-response-columns", required=True)
@click.argument("voice-name", required=True)
@click.option(
    "--remove-silence/--no-remove-silence",
    default=True,
    help="Whether to remove silence from audio recordings. Defaults to True.",
)
@click.option(
    "--max-concurrent",
    default=30,
    help="Maximum number of concurrent requests to TTS API. Defaults to 30.",
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
def save_chatbot_response_recordings_locally(
    responses_file_path: str,
    intent_name_column: str,
    intent_response_columns: str,
    voice_name: str,
    remove_silence: bool,
    max_concurrent: int,
    save_recordings_to: str,
    skip_fillers: bool,
    only_fillers: bool,
) -> None:
    """Generates speech recordings from chatbot responses and saves them locally."""
    available_voices = get_available_voice_names()
    if voice_name not in available_voices:
        raise click.BadParameter(f"Voice '{voice_name}' not found. Available voices: {available_voices}")

    voice_config = get_voice_config(voice_name)
    voice_id = voice_config["id"]

    intent_response_columns_list = intent_response_columns.split(",")

    if only_fillers:
        intent_response_columns_list = [c for c in intent_response_columns_list if c.startswith("filler_word_")]
    elif skip_fillers:
        intent_response_columns_list = [c for c in intent_response_columns_list if not c.startswith("filler_word_")]

    if not intent_response_columns_list:
        return None

    chatbot_responses = pd.read_csv(responses_file_path)

    base_path = Path(save_recordings_to)

    async def main() -> None:
        for intent_response_column in tqdm(intent_response_columns_list):
            await process_responses_async(
                chatbot_responses,
                intent_response_column,
                intent_name_column,
                voice_id,
                voice_name,
                remove_silence,
                base_path,
                max_concurrent,
            )

    asyncio.run(main())
    click.echo("Local text-to-speech generation completed.")


if __name__ == "__main__":
    save_chatbot_response_recordings_locally()
