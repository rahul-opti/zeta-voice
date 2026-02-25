import json
from collections.abc import Iterator
from typing import cast

from elevenlabs import VoiceSettings
from elevenlabs.client import AsyncElevenLabs, ElevenLabs
from loguru import logger

from carriage_services.paths import PROJECT_PATH
from carriage_services.settings import ElevenLabsTTSSettings, settings


def _load_voice_settings(config_name: str = "Maria") -> VoiceSettings:
    """Load voice settings from JSON config file."""
    config_path = PROJECT_PATH / "config" / "elevenlabs_voice_settings" / f"{config_name}.json"

    try:
        with open(config_path, encoding="utf-8") as f:
            voice_config = json.load(f)

        return VoiceSettings(
            stability=voice_config.get("stability", 0.9),
            similarity_boost=voice_config.get("similarity_boost", 0.85),
            style=voice_config.get("style", 0.1),
            use_speaker_boost=voice_config.get("use_speaker_boost", True),
            speed=voice_config.get("speed", 1.0),
        )
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        # Fallback to default settings if config file is missing or invalid
        logger.error(f"Error loading config: {config_path} {e} Using default config")
        return VoiceSettings(
            stability=0.9,
            similarity_boost=0.85,
            style=0.1,
            use_speaker_boost=True,
            speed=1.0,
        )


def generate_speech(
    text: str,
    tts_model: str = "eleven_flash_v2_5",
    voice: str = "uFIXVu9mmnDZ7dTKCBTX",
    config_name: str = "Maria",
) -> Iterator[bytes]:
    """
    Generate speech from text using ElevenLabs TTS API and return raw audio bytes.
    """
    # Narrow type for mypy
    tts_settings = cast(ElevenLabsTTSSettings, settings.tts)
    client = ElevenLabs(api_key=tts_settings.ELEVENLABS_API_KEY)
    voice_settings = _load_voice_settings(config_name)

    audio_bytes = client.text_to_speech.convert(
        text=text,
        model_id=tts_model,
        voice_id=voice,
        output_format="mp3_44100_128",
        voice_settings=voice_settings,
    )
    return audio_bytes


async def async_generate_speech(
    text: str,
    tts_model: str = "eleven_flash_v2_5",
    voice: str = "uFIXVu9mmnDZ7dTKCBTX",
    config_name: str = "Maria",
) -> bytes:
    """
    Asynchronously generate speech from text using ElevenLabs TTS API and return raw audio bytes.
    """
    # Same as above, using typing.cast
    tts_settings = cast(ElevenLabsTTSSettings, settings.tts)
    client = AsyncElevenLabs(api_key=tts_settings.ELEVENLABS_API_KEY)
    voice_settings = _load_voice_settings(config_name)

    audio_chunks = []
    async for chunk in client.text_to_speech.convert(
        text=text,
        model_id=tts_model,
        voice_id=voice,
        output_format="mp3_44100_128",
        voice_settings=voice_settings,
    ):
        audio_chunks.append(chunk)

    # Combine all chunks into a single bytes object
    audio_bytes = b"".join(audio_chunks)
    return audio_bytes
