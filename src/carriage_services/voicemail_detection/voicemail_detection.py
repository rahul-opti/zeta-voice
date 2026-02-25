import re

import pandas as pd
from jinja2 import Environment, FileSystemLoader
from litellm import acompletion
from loguru import logger
from pydantic import BaseModel

from carriage_services.paths import VOICEMAIL_DETECTION_PROMPT_PATH, VOICEMAIL_RESPONSES_PATH
from carriage_services.settings import settings


class VoicemailDetectionResult(BaseModel):
    """Result of voicemail detection analysis."""

    is_voicemail: bool


class VoicemailDetector:
    """
    Detects voicemail systems and answering machines from call transcriptions.

    Uses either rule-based pattern matching or LLM-based analysis to determine
    if a call recipient is a voicemail system, answering machine, or live person
    based on text transcriptions. The detection method is controlled by the
    VOICEMAIL_DETECTOR_TYPE setting.
    """

    def __init__(self) -> None:
        """
        Initialize the voicemail detector.
        """
        self.detector_type = settings.voicemail_detection.VOICEMAIL_DETECTOR_TYPE

        if self.detector_type == "llm":
            self._prompt_template = Environment(loader=FileSystemLoader(searchpath="/"), autoescape=True).get_template(
                str(VOICEMAIL_DETECTION_PROMPT_PATH),
            )

        elif self.detector_type == "rule_based":
            self._load_voicemail_patterns()
        else:
            raise ValueError(f"Unknown detector type: {self.detector_type}")

    def _load_voicemail_patterns(self) -> None:
        """Load voicemail detection patterns from CSV file."""
        voicemail_df = pd.read_csv(str(VOICEMAIL_RESPONSES_PATH))
        self.voicemail_patterns = set(voicemail_df["Voicemail"].dropna().str.lower())
        logger.info("Voicemail detection patterns loaded successfully.")

    async def detect_voicemail(self, transcription: str) -> VoicemailDetectionResult | None:
        """
        Detect if the call recipient is a voicemail system.

        Args:
            transcription: The text transcription of the call to analyze.

        Returns:
            VoicemailDetectionResult with detection results, or None if detection fails.
        """
        if not transcription or not transcription.strip():
            logger.warning("Empty transcription provided for voicemail detection")
            return None

        try:
            if self.detector_type == "rule_based":
                is_voicemail = self._detect_voicemail_rule_based(transcription)
                logger.info(f"Rule-based voicemail detection completed: is_voicemail={is_voicemail}")
                return VoicemailDetectionResult(is_voicemail=is_voicemail)
            elif self.detector_type == "llm":
                return await self._detect_voicemail_llm(transcription)
            else:
                logger.error(f"Unknown detector type: {self.detector_type}")
                return None
        except Exception as e:
            logger.error(f"Error during voicemail detection: {e}")
            return None

    def _detect_voicemail_rule_based(self, transcription: str) -> bool:
        """
        Detect voicemail using rule-based pattern matching.

        Args:
            transcription: The text transcription to analyze.

        Returns:
            True if voicemail detected, False otherwise.
        """
        if not hasattr(self, "voicemail_patterns") or not self.voicemail_patterns:
            return False

        message_clean = re.sub(r"[^\w\s]", "", transcription.lower().strip())

        def _matches_patterns(patterns: set[str], text: str) -> bool:
            for pattern in patterns:
                if " " in pattern and pattern in text:
                    return True
            text_words = set(text.split())
            return any(pattern in text_words for pattern in patterns if " " not in pattern)

        return _matches_patterns(self.voicemail_patterns, message_clean)

    async def _detect_voicemail_llm(self, transcription: str) -> VoicemailDetectionResult | None:
        """
        Detect voicemail using LLM-based analysis.

        Args:
            transcription: The text transcription to analyze.

        Returns:
            VoicemailDetectionResult with detection results, or None if detection fails.
        """
        prompt = self._prompt_template.render(transcription=transcription)

        logger.debug(f"Voicemail detection prompt: {prompt}")

        response = await acompletion(
            model=settings.voicemail_detection.VOICEMAIL_DETECTION_MODEL,
            messages=[{"content": prompt, "role": "user"}],
            response_format=VoicemailDetectionResult,
        )

        result = VoicemailDetectionResult.model_validate_json(response.choices[0].message.content)
        logger.info(f"LLM voicemail detection completed: is_voicemail={result.is_voicemail}")

        return result
