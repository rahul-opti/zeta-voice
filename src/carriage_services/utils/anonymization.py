import logging
from asyncio import get_running_loop

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

# Disable or reduce Presidio logging
logging.getLogger("presidio-analyzer").setLevel(logging.CRITICAL)
logging.getLogger("presidio-anonymizer").setLevel(logging.CRITICAL)
logging.getLogger("presidio_analyzer").setLevel(logging.CRITICAL)
logging.getLogger("presidio_anonymizer").setLevel(logging.CRITICAL)

analyzer = AnalyzerEngine()
anonymizer = AnonymizerEngine()
operators = {
    "DEFAULT": OperatorConfig("replace", {"new_value": "<ANONYMIZED>"}),
    "PERSON": OperatorConfig("replace", {"new_value": "<PERSON>"}),
    "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "<PHONE_NUMBER>"}),
    "LOCATION": OperatorConfig("replace", {"new_value": "<LOCATION>"}),
    "DATE_TIME": OperatorConfig("replace", {"new_value": "<DATE_TIME>"}),
    "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "<EMAIL_ADDRESS>"}),
    "NRP": OperatorConfig("replace", {"new_value": "<NRP>"}),
}


def _anonymize_text_sync(text: str) -> str:
    """
    Anonymize PII in text using Presidio anonymizer.

    Args:
        text: Input text to anonymize
    Returns:
        Anonymized text
    """
    analyzer_results = analyzer.analyze(text=text, language="en")
    anonymized_text = anonymizer.anonymize(text=text, analyzer_results=analyzer_results, operators=operators)

    return anonymized_text.text


async def anonymize_text(text: str) -> str:
    """
    Anonymize PII in text using Presidio anonymizer asynchronously.

    Args:
        text: Input text to anonymize
    Returns:
        Anonymized text
    """
    loop = get_running_loop()
    return await loop.run_in_executor(None, _anonymize_text_sync, text)
