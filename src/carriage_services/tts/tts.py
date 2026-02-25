import json
import uuid
from abc import ABC, abstractmethod

from carriage_services.audio.silence_remover import SilenceRemover
from carriage_services.paths import ELEVENLABS_VOICES_PATH
from carriage_services.settings import ElevenLabsTTSSettings, settings
from carriage_services.tts.elevenlabs_tts import async_generate_speech as elevenlabs_async_generate_speech
from carriage_services.tts.openai_tts import async_generate_speech as openai_async_generate_speech
from carriage_services.utils.recordings_storage import AzureBlobStorage


def _load_elevenlabs_voices() -> list[dict]:
    """Load ElevenLabs voice configurations from JSON file."""
    with open(ELEVENLABS_VOICES_PATH, encoding="utf-8") as f:
        config = json.load(f)
    return config["voices"]


def get_voice_config(voice_name: str) -> dict:
    """Get voice config by name."""
    voices = _load_elevenlabs_voices()
    for voice in voices:
        if voice["name"] == voice_name:
            return voice
    available_names = [v["name"] for v in voices]
    raise ValueError(f"Voice not found: {voice_name}. Available: {available_names}")


class TTSService(ABC):
    """Abstract base class for Text-to-Speech services."""

    @abstractmethod
    async def generate_recording(self, text: str) -> str:
        """
        Generates speech and uploads it to the dynamic container.

        Args:
            text (str): The text to be converted to speech

        Returns:
            str: URL to the generated audio file
        """
        pass

    @abstractmethod
    def get_recording_url(self, intent_name: str, utterance_name: str) -> str:
        """
        Returns url to speech recording in static container.

        Args:
            intent_name (str): The name of the intent
            utterance_name (str): The name of the utterance

        Returns:
            str: URL to file with bot response recording
        """
        pass

    @abstractmethod
    async def generate_and_save_recording(
        self, text: str, intent_name: str, utterance_name: str, remove_silence: bool = True
    ) -> None:
        """
        Generates speech and saves it to the static container.

        Args:
            text (str): The text to be converted to speech
            intent_name (str): The name of the intent
            utterance_name (str): The name of the utterance
            remove_silence (bool): Whether to remove silence from the audio. Defaults to True.
        """
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """
        Cleans up resources, particularly the blob service client.
        """
        pass


class OpenAITTSService(TTSService):
    """OpenAI TTS service implementation that uses Azure Blob Storage."""

    def __init__(self, bot_gender: str | None = None) -> None:
        self.silence_remover = SilenceRemover()
        self.recordings_storage = AzureBlobStorage()
        self.base_url = settings.telephony.BASE_URL
        self.static_container_name = settings.storage.AZURE_STORAGE_STATIC_CONTAINER_NAME_OAI
        self.dynamic_container_name = settings.storage.LOCAL_STORAGE_DYNAMIC_CONTAINER_NAME
        self.tts_model = settings.tts.TTS_MODEL

        self.gender_choice = bot_gender
        if self.gender_choice == "female":
            self.tts_voice = settings.tts.TTS_VOICE_FEMALE
        elif self.gender_choice == "male":
            self.tts_voice = settings.tts.TTS_VOICE_MALE
        else:
            raise ValueError(f"Invalid voice choice: {self.gender_choice}")

    def _get_recording_name(self, intent_name: str, utterance_name: str) -> str:
        """Get the recording name."""
        return f"{self.tts_voice}/{intent_name}/{utterance_name}.mp3"

    async def generate_recording(self, text: str) -> str:
        """Generates speech and saves it to the dynamic folder."""
        file_name = f"{uuid.uuid4()}.mp3"
        audio_bytes = await openai_async_generate_speech(text, self.tts_model, self.tts_voice)
        file_path = f"{self.dynamic_container_name}/{file_name}"
        with open(file_path, "wb") as f:
            f.write(audio_bytes)
        return str(self.base_url) + "/dynamic-recordings/" + file_name

    async def generate_and_save_recording(
        self, text: str, intent_name: str, utterance_name: str, remove_silence: bool = True
    ) -> None:
        """Generates speech, optionally removes silence and saves it to the static container."""
        blob_name = self._get_recording_name(intent_name, utterance_name)
        audio_bytes = await openai_async_generate_speech(text, self.tts_model, self.tts_voice)

        if remove_silence:
            processed_bytes = self.silence_remover.remove_silence_from_bytes(audio_bytes, original_format="mp3")
        else:
            processed_bytes = audio_bytes

        await self.recordings_storage.async_upload_to_blob_audio(processed_bytes, self.static_container_name, blob_name)

    def get_recording_url(self, intent_name: str, utterance_name: str) -> str:
        """Returns url to speech recording in static container."""
        blob_name = self._get_recording_name(intent_name, utterance_name)
        return self.recordings_storage.get_public_url(self.static_container_name, blob_name)

    async def cleanup(self) -> None:
        """Clean up resources, particularly the blob service client."""
        await self.recordings_storage.cleanup()


class ElevenLabsTTSService(TTSService):
    """11labs TTS service implementation that uses Azure Blob Storage."""

    def __init__(self, voice_name: str) -> None:
        self.silence_remover = SilenceRemover()
        self.recordings_storage = AzureBlobStorage()
        self.base_url = settings.telephony.BASE_URL
        self.static_container_name = settings.storage.AZURE_STORAGE_STATIC_CONTAINER_NAME_11LABS
        self.dynamic_container_name = settings.storage.LOCAL_STORAGE_DYNAMIC_CONTAINER_NAME
        self.tts_model = settings.tts.TTS_MODEL

        voice_config = get_voice_config(voice_name)
        self.tts_voice = voice_config["id"]
        self.voice_name = voice_name

    def _get_recording_name(self, intent_name: str, utterance_name: str) -> str:
        """Get the recording name."""
        return f"{self.tts_voice}/{intent_name}/{utterance_name}.mp3"

    async def generate_recording(self, text: str) -> str:
        """Generates speech and saves it to the dynamic folder."""
        file_name = f"{uuid.uuid4()}.mp3"
        audio_bytes = await elevenlabs_async_generate_speech(text, self.tts_model, self.tts_voice, self.voice_name)
        file_path = f"{self.dynamic_container_name}/{file_name}"
        with open(file_path, "wb") as f:
            f.write(audio_bytes)
        return str(self.base_url) + "/dynamic-recordings/" + file_name

    async def generate_and_save_recording(
        self, text: str, intent_name: str, utterance_name: str, remove_silence: bool = True
    ) -> None:
        """Generates speech, optionally removes silence and saves it to the static container."""
        blob_name = self._get_recording_name(intent_name, utterance_name)

        # Use fillers settings for filler_word columns, regular settings for everything else
        config_name = f"{self.voice_name}_fillers" if "filler_word" in utterance_name else self.voice_name
        audio_bytes = await elevenlabs_async_generate_speech(text, self.tts_model, self.tts_voice, config_name)

        if remove_silence:
            processed_bytes = self.silence_remover.remove_silence_from_bytes(audio_bytes, original_format="mp3")
        else:
            processed_bytes = audio_bytes

        await self.recordings_storage.async_upload_to_blob_audio(processed_bytes, self.static_container_name, blob_name)

    def get_recording_url(self, intent_name: str, utterance_name: str) -> str:
        """Returns url to speech recording in static container."""
        blob_name = self._get_recording_name(intent_name, utterance_name)
        return self.recordings_storage.get_public_url(self.static_container_name, blob_name)

    async def cleanup(self) -> None:
        """Clean up resources, particularly the blob service client."""
        await self.recordings_storage.cleanup()


def create_tts_service(voice_name: str) -> TTSService:
    """Factory function to create the appropriate TTS service based on TTS_PROVIDER setting."""
    if isinstance(settings.tts, ElevenLabsTTSSettings):
        return ElevenLabsTTSService(voice_name)
    return OpenAITTSService(voice_name)


def get_available_voice_names() -> list[str]:
    """Get list of available ElevenLabs voice names from config."""
    voices = _load_elevenlabs_voices()
    return [voice["name"] for voice in voices]
