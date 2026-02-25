#!/usr/bin/env python3

import asyncio
from pathlib import Path

import click

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


async def _generate_audio_bytes(text: str, voice_id: str, voice_name: str) -> bytes:
    if isinstance(settings.tts, ElevenLabsTTSSettings):
        return await elevenlabs_async_generate_speech(text, settings.tts.TTS_MODEL, voice_id, voice_name)
    return await openai_async_generate_speech(text, settings.tts.TTS_MODEL, voice_id)


@click.command()
@click.option("--utterance", required=True, help="Text to synthesize into a single audio file.")
@click.option(
    "--voice-name",
    default="Maria",
    help="Voice name from config/elevenlabs_voices.json (e.g., Maria, Alex, Luke).",
)
@click.option("--remove-silence/--no-remove-silence", default=True, help="Trim leading/trailing silence.")
@click.option(
    "--save-to",
    default="data/single_recording/output.mp3",
    help="Path to save the generated MP3. Defaults to data/single_recording/output.mp3.",
)
def main(utterance: str, voice_name: str, remove_silence: bool, save_to: str) -> None:
    """Generate a single local TTS recording and save to the specified path."""
    available_voices = get_available_voice_names()
    if voice_name not in available_voices:
        raise click.BadParameter(f"Voice '{voice_name}' not found. Available voices: {available_voices}")

    voice_config = get_voice_config(voice_name)
    voice_id = voice_config["id"]

    async def run() -> None:
        audio_bytes = await _generate_audio_bytes(utterance, voice_id, voice_name)
        if remove_silence:
            processed_bytes = SilenceRemover().remove_silence_from_bytes(audio_bytes, original_format="mp3")
        else:
            processed_bytes = audio_bytes

        target = Path(save_to)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(processed_bytes)

    asyncio.run(run())
    click.echo(f"Saved: {save_to}")


if __name__ == "__main__":
    main()
