"""Audio silence removal utilities."""

import io

from loguru import logger
from pydub import AudioSegment
from pydub.silence import detect_nonsilent


class SilenceRemover:
    """Handles removal of silence from audio segments."""

    def __init__(self, silence_thresh: int = -40, min_silence_len: int = 100, padding: int = 150) -> None:
        """
        Initialize the silence remover with default parameters.

        Args:
            silence_thresh: The silence threshold in dBFS (default: -40)
            min_silence_len: Minimum length of silence in ms to be considered silence (default: 100)
            padding: Padding in ms to keep around non-silent parts (default: 150)
        """
        self.silence_thresh = silence_thresh
        self.min_silence_len = min_silence_len
        self.padding = padding

    def remove_silence_from_audio(self, audio: AudioSegment) -> AudioSegment:
        """
        Remove silence from the beginning and end of an audio segment.

        Args:
            audio: The audio segment to process

        Returns:
            AudioSegment with silence removed from beginning and end
        """
        try:
            nonsilent_chunks = detect_nonsilent(
                audio, min_silence_len=self.min_silence_len, silence_thresh=self.silence_thresh
            )

            if not nonsilent_chunks:
                logger.warning("No non-silent chunks found in audio, returning first 100ms")
                return audio[:100]

            start_trim = max(0, nonsilent_chunks[0][0] - self.padding)
            end_trim = min(len(audio), nonsilent_chunks[-1][1] + self.padding)

            original_length = len(audio)
            trimmed_audio = audio[start_trim:end_trim]
            new_length = len(trimmed_audio)

            logger.debug(
                f"Silence removal: {original_length/1000:.2f}s -> {new_length/1000:.2f}s "
                f"(removed {(original_length - new_length)/1000:.2f}s)"
            )

            return trimmed_audio

        except Exception as e:
            logger.error(f"Failed to remove silence from audio: {e}. Returning original audio.")
            return audio

    def remove_silence_from_bytes(self, audio_bytes: bytes, original_format: str = "mp3") -> bytes:
        """
        Remove silence from audio bytes and return processed bytes.

        Args:
            audio_bytes: The raw audio data as bytes
            original_format: The format of the input audio (e.g., 'mp3', 'wav')

        Returns:
            The processed audio data as bytes in the same format
        """
        try:
            audio_segment = AudioSegment.from_file(io.BytesIO(audio_bytes), format=original_format)

            processed_audio = self.remove_silence_from_audio(audio_segment)

            buffer = io.BytesIO()
            processed_audio.export(buffer, format=original_format)
            return buffer.getvalue()

        except Exception as e:
            logger.error(f"Failed to process audio bytes: {e}. Returning original bytes.")
            return audio_bytes
