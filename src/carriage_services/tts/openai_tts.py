from typing import cast

from openai import AsyncOpenAI, OpenAI

from carriage_services.settings import OpenAITTSSettings, settings

VOICE_INSTRUCTIONS = """
Voice: Warm, empathetic, and professional, reassuring the customer that their issue is
understood and will be resolved.
Punctuation: Well-structured with natural pauses, allowing for clarity and a steady,
calming flow.
Delivery: Calm and patient, with a supportive and understanding tone that reassures
the listener.
Phrasing: Clear and concise, using customer-friendly language that avoids jargon
while maintaining professionalism.
Tone: Empathetic and solution-focused, emphasizing both understanding and proactive
assistance.
"""


def generate_speech(text: str, tts_model: str = "gpt-4o-mini-tts", voice: str = "alloy") -> bytes:
    """
    Generate speech from text using OpenAI's TTS API and return raw audio bytes.
    """
    # Narrow type for mypy
    tts_settings = cast(OpenAITTSSettings, settings.tts)
    client = OpenAI(api_key=tts_settings.OPENAI_API_KEY)

    response = client.audio.speech.create(
        model=tts_model, voice=voice, input=text, response_format="mp3", instructions=VOICE_INSTRUCTIONS
    )
    audio_bytes = response.content
    return audio_bytes


async def async_generate_speech(text: str, tts_model: str = "gpt-4o-mini-tts", voice: str = "alloy") -> bytes:
    """
    Asynchronously generate speech from text using OpenAI's TTS API and return raw audio bytes.
    """
    # Same as above, using typing.cast
    tts_settings = cast(OpenAITTSSettings, settings.tts)
    client = AsyncOpenAI(api_key=tts_settings.OPENAI_API_KEY)

    async with client.audio.speech.with_streaming_response.create(
        model=tts_model, voice=voice, input=text, response_format="mp3", instructions=VOICE_INSTRUCTIONS
    ) as response:
        audio_bytes = await response.read()
    return audio_bytes
