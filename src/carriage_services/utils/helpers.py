import ast
import json
import random
import re
import uuid
from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class Utterance:
    """Utterance class."""

    utterance_name: str
    utterance_content: str
    intro_content: str = ""


@dataclass
class Response(Utterance):
    """Response class."""

    intent_name: str = ""


def default_uuid() -> uuid.UUID:
    """Generate a default UUID object."""
    return uuid.uuid4()


def fetch_lead_data() -> dict[str, Any]:
    """Mock API call to fetch lead data."""
    return {
        "lead_id": "12345",
        "phone": "+1234567890",
        "email": "john.doe@example.com",
        "interest_level": "high",
        "source": "online_form",
        "funeral_home_name": "Bradshaw Carter Funeral Home",
        "funeral_home_address": "123 Main St, Anytown, USA",
        "user_name": "John Doe",
    }


def parse_required_slots(required_slots_str: str) -> list[tuple[str, Any]]:
    """Parse required_slots string into list of tuples.

    Args:
        required_slots_str: String representation of required slots, e.g., '[("confirm_identity", False)]'

    Returns:
        List of tuples containing slot name and expected value pairs.
        Returns empty list if parsing fails or input is empty/null.

    """
    if pd.isna(required_slots_str) or not required_slots_str.strip():
        return []
    try:
        return ast.literal_eval(required_slots_str)
    except (ValueError, SyntaxError):
        return []


def filter_and_sample_responses(row: pd.Series, include_intro: bool = True) -> Utterance:
    """Filter out empty/null responses from a DataFrame row and randomly sample one.

    Args:
        row: Pandas Series containing response columns (example_chatbot_response_1 through example_chatbot_response_5)
        include_intro: Whether to include intro part in the final response

    Returns:
        Randomly selected non-empty response string, optionally combined with intro part

    Raises:
        ValueError: If no valid responses are found for the slot
    """
    response_columns = [f"example_chatbot_response_{i}" for i in range(1, 6)]

    responses = []
    for col in response_columns:
        if col in row:
            response = _get_bot_response(row, col)
            if response:
                responses.append(response)

    if not responses:
        raise ValueError(f"No responses found for slot: {row.name}")

    random_response = random.choice(responses)

    # Combine with intro response if requested and available
    intro_content = ""
    if include_intro and "intro_chatbot_response" in row:
        intro_response = _get_bot_response(row, "intro_chatbot_response")
        intro_content = intro_response[1] if intro_response else ""

    return Utterance(
        utterance_name=random_response[0], utterance_content=random_response[1], intro_content=intro_content
    )


def _get_bot_response(row: pd.Series, col: str) -> tuple[str, str] | None:
    """Get bot response for a given row and column."""
    value = row[col]
    if isinstance(value, pd.Series):
        value = value.iloc[0]
    if pd.notna(value) and str(value).strip():
        return (col, str(value))
    return None


def load_utterances_config(config_path: str) -> pd.DataFrame:
    """Load and process utterances configuration from CSV file.

    Args:
        config_path: Path to the CSV file containing utterances configuration

    Returns:
        Processed pandas DataFrame with:
        - required_slots column transformed from string to list of tuples
        - sampled_response column containing randomly sampled responses
    """
    df = pd.read_csv(config_path)
    df["required_slots"] = df["required_slots"].apply(parse_required_slots)
    df = df.set_index("slot_name")

    return df


def load_json(file_path: str) -> dict[str, Any]:
    """Load JSON file and return as dictionary."""
    try:
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def generate_intro_message_description(intro_messages_path: str) -> str:
    """Generate description for intro message versions from JSON config."""
    intro_config = load_json(intro_messages_path)
    versions = intro_config.get("versions", {})

    description_parts = ["Optional version of the intro message to use. Available options:\n\n"]

    for key, data in versions.items():
        message = data.get("message", "")
        description_parts.append(f'• **{key}**: "{message}"\n\n')

    description_parts.append("If not provided, will use the default version.")
    return "".join(description_parts)


def convert_numbers_to_string_digits(data: dict[str, Any]) -> dict[str, Any]:
    """Convert numeric values and numbers in strings to their digit word representation.

    For numeric types (int, float): converts the entire number.
    For strings: converts any numeric sequences found within the string.
    Example: "2052 Howard Road" -> "two zero five two Howard Road"
    """
    digit_mapping = {
        "0": "zero",
        "1": "one",
        "2": "two",
        "3": "three",
        "4": "four",
        "5": "five",
        "6": "six",
        "7": "seven",
        "8": "eight",
        "9": "nine",
    }

    def replace_digit(match: re.Match[str]) -> str:
        """Replace a single digit/character with its word representation."""
        char = match.group(0)
        return " " + digit_mapping.get(char, char)

    def convert_number_sequence(match: re.Match[str]) -> str:
        """Convert a sequence of digits in a string to word form."""
        number_str = match.group(0)
        converted = re.sub(r"[0-9.\-]", replace_digit, number_str).strip()
        return re.sub(r"\s+", " ", converted)

    def convert_value(value: Any) -> Any:
        """Convert any value, handling different data types."""
        # Check for bool first since bool is a subclass of int in Python
        if isinstance(value, bool):
            return value
        elif isinstance(value, (int | float)):
            # Convert number to string of digits using regex
            str_value = str(value)
            converted_value = re.sub(r"[0-9.\-]", replace_digit, str_value).strip()
            return re.sub(r"\s+", " ", converted_value)
        elif isinstance(value, str):
            # Skip UUID-like strings (contains hyphens and hex characters)
            if re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", value.lower()):
                return value
            # Convert numeric sequences within strings (like addresses)
            return re.sub(r"\d+", convert_number_sequence, value)
        elif isinstance(value, dict):
            # Recursively convert nested dictionaries
            return {k: convert_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            # Recursively convert lists
            return [convert_value(item) for item in value]
        elif isinstance(value, tuple):
            # Recursively convert tuples (return as tuple)
            return tuple(convert_value(item) for item in value)
        elif isinstance(value, set):
            # Recursively convert sets (return as set)
            return {convert_value(item) for item in value}
        else:
            # Return other types unchanged (None, custom objects, etc.)
            return value

    return convert_value(data)
