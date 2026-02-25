import re

import pandas as pd
from loguru import logger

from carriage_services.paths import RULE_BASED_ENGLISH_RESPONSES_PATH


class RuleBasedEnglishClassifier:
    """Classifies user input as affirmative or negative based on a predefined list of words."""

    def __init__(self) -> None:
        """Initializes the SimpleClassifier by loading affirmative and negative words from a CSV."""
        try:
            df = pd.read_csv(str(RULE_BASED_ENGLISH_RESPONSES_PATH))
            self.affirmative_words = set(df["Affirm"].dropna().str.lower())
            self.negative_words = set(df["Deny"].dropna().str.lower())
            self.goodbye_words = set(df["Goodbye"].dropna().str.lower())
            self.who_words = set(df["Who"].dropna().str.lower())
            logger.info("Simple classifier initialized with affirmative, negative, goodbye, and who words.")
        except FileNotFoundError:
            logger.warning(
                f"Simple responses file not found at {RULE_BASED_ENGLISH_RESPONSES_PATH}. "
                "Simple classifier will be disabled."
            )
            self.affirmative_words = set()
            self.negative_words = set()
            self.goodbye_words = set()
            self.who_words = set()
        except Exception as e:
            logger.error(f"Error initializing SimpleClassifier: {e}")
            self.affirmative_words = set()
            self.negative_words = set()
            self.goodbye_words = set()
            self.who_words = set()

    def classify(self, user_message: str) -> bool | str | None:
        """
        Classifies a user message as affirmative, negative, or neither by checking for keywords.

        This method checks for both multi-word phrases and individual words while
        avoiding partial matches (e.g., 'no' in 'know'). When both affirmative and
        negative patterns are detected, it returns None to indicate ambiguity.

        Args:
            user_message: The user's utterance.

        Returns:
            True if affirmative, False if negative, None if ambiguous or no match.
        """
        if not self.affirmative_words and not self.negative_words:
            return None

        message_clean = re.sub(r"[^\w\s]", "", user_message.lower().strip())

        # Helper function to check if any pattern matches
        def _matches_patterns(patterns: set[str], text: str) -> bool:
            # Check phrases first (they contain spaces)
            for pattern in patterns:
                if " " in pattern and pattern in text:
                    return True

            # Then check individual words
            text_words = set(text.split())
            return any(pattern in text_words for pattern in patterns if " " not in pattern)

        has_affirmative = _matches_patterns(self.affirmative_words, message_clean)
        has_negative = _matches_patterns(self.negative_words, message_clean)
        is_goodbye = _matches_patterns(self.goodbye_words, message_clean)
        is_who = _matches_patterns(self.who_words, message_clean)

        if is_goodbye:
            return "goodbye"

        if is_who:
            return "who_is_this"

        # If both patterns are found, return None to indicate ambiguity
        if has_affirmative and has_negative:
            return None

        if has_affirmative:
            return True
        if has_negative:
            return False

        return None
