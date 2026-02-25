from jinja2 import Environment, FileSystemLoader
from litellm import completion
from loguru import logger

from carriage_services.paths import REPHRASE_PROMPT_PATH
from carriage_services.settings import RephraserSettings
from carriage_services.utils.helpers import Utterance


class Rephraser:
    """Service to rephrase bot messages for better user experience."""

    def __init__(self) -> None:
        self.settings = RephraserSettings()
        self._rephrase_template = Environment(loader=FileSystemLoader(searchpath="/"), autoescape=True).get_template(
            str(REPHRASE_PROMPT_PATH)
        )

    def rephrase(self, new_bot_message: str, previous_bot_message: str) -> Utterance:
        """Rephrase the user message using the rephrase template."""
        prompt = self._rephrase_template.render(
            new_bot_message=new_bot_message, previous_bot_message=previous_bot_message
        )
        logger.info(prompt)
        response = completion(
            model=self.settings.REPHRASER_MODEL,
            messages=[{"content": prompt, "role": "user"}],
        )
        message = response.choices[0].message.content
        logger.info(f"Rephrased message: {message}")

        return Utterance(
            utterance_name="booking_response",
            utterance_content=message,
        )
