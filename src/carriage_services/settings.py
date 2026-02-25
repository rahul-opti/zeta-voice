import csv
import json
import os

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from carriage_services.paths import SLOTS_WITH_RESPONSES_PATH
from carriage_services.utils.azure import get_main_service_url
from carriage_services.utils.enums import BookingFlowPersona


class AuthSettings(BaseSettings):
    """Settings for API authentication."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    ADMIN_API_KEY: str | None = None
    USER_API_KEY: str | None = None


class EngineSettings(BaseSettings):
    """Settings for database."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    POSTGRES_HOST: str | None = None
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str | None = None
    POSTGRES_USER: str | None = None
    POSTGRES_PASSWORD: str | None = None

    DB_PATH: str = "data/carriage.db"

    @computed_field
    def DATABASE_URL(self) -> str:
        """
        Constructs the database URL.
        """
        if all([self.POSTGRES_HOST, self.POSTGRES_DB, self.POSTGRES_USER, self.POSTGRES_PASSWORD]):
            return (
                f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )

        if "://" in self.DB_PATH:
            return self.DB_PATH

        return f"sqlite+pysqlite:///{self.DB_PATH}"


class TelephonySettings(BaseSettings):
    """Settings for Twilio telephony provider."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    TWILIO_ACCOUNT_SID: str
    TWILIO_AUTH_TOKEN: str
    TWILIO_PHONE_NUMBERS: str
    TWILIO_TTS_VOICE: str = "alice"
    TIMEOUT: int = 7
    FIRST_MESSAGE_DELAY_SECONDS: int = 2
    COMFORT_NOISE_FILENAME: str = "noise.mp3"
    ENABLE_COMFORT_NOISE: bool = False

    @computed_field
    def available_phone_numbers(self) -> list[str]:
        """Get list of available Twilio phone numbers from JSON array."""
        return json.loads(self.TWILIO_PHONE_NUMBERS)

    @computed_field
    def default_phone_number(self) -> str | None:
        """Get the default (first) phone number."""
        numbers: list[str] = self.available_phone_numbers  # type: ignore[assignment]
        return numbers[0] if numbers else None

    # Flow interruption settings - True allows immediate interruption, False requires sound to complete
    FLOW_INTERRUPTION_SETTINGS: dict[str, bool] = {
        "booking_flow": True,
        "booking_flow_completed": True,
        "accept_appointment": True,
        "offer_rebuttal": True,
        "question_flow_completed": True,
    }

    @computed_field
    def BASE_URL(self) -> str:  # noqa
        """Constructs the base URL for the telephony service."""
        url = get_main_service_url(
            container_app_name=os.environ.get("APP_NAME", "name") + "-app",
            subscription_id=os.environ.get("ARM_SUBSCRIPTION_ID", ""),
            resource_group=os.environ.get("RESOURCE_GROUP_NAME", ""),
            tenant_id=os.environ.get("ARM_TENANT_ID", ""),
            client_id=os.environ.get("ARM_CLIENT_ID", ""),
            client_secret=os.environ.get("ARM_CLIENT_SECRET", ""),
        )
        if url is None:
            return os.environ.get("BASE_URL", "http://localhost:8000")
        return url


class ConversationSettings(BaseSettings):
    """Settings for conversation system."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    MAX_TURNS: int = 100
    LLM_ANALYZED_TURNS: int = 5

    MAX_WORDS_FOR_SIMPLE_CLASSIFIER: int = 4

    TRANSCRIPTION_CONFIDENCE_THRESHOLD: float = 0.30
    FIRST_MESSAGE_INTERRUPTION_SECONDS: float = 10.0

    @computed_field
    def NUMBER_OF_FILLER_WORDS_OPTIONS(self) -> int:  # noqa: PLR6301
        """Get number of filler word columns from slots_with_responses.csv file."""
        try:
            with open(SLOTS_WITH_RESPONSES_PATH, encoding="utf-8") as file:
                reader = csv.reader(file)
                header = next(reader)
                filler_word_columns = [col for col in header if col.startswith("filler_word_")]
                return len(filler_word_columns)
        except (FileNotFoundError, StopIteration, OSError):
            return 3


class IntentClassificationSettings(BaseSettings):
    """Settings for intent classification service."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    INTENT_CLASSIFICATION_MODEL: str = "gpt-4o-2024-08-06"
    INTENT_CLASSIFICATION_TEMPERATURE: float = 0.05
    QUESTION_CLASSIFICATION_MODEL: str = "gpt-4o-mini"
    OBJECTION_CLASSIFICATION_MODEL: str = "gpt-4o-mini"
    OPENAI_API_KEY: str


class VoicemailDetectionSettings(BaseSettings):
    """Settings for voicemail detection service."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    VOICEMAIL_DETECTOR_TYPE: str = "rule_based"  # Options: "rule_based" or "llm"
    VOICEMAIL_DETECTION_MODEL: str = "gpt-4o-2024-08-06"
    OPENAI_API_KEY: str


class ElevenLabsTTSSettings(BaseSettings):
    """Settings for 11Labs TTS service."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    TTS_MODEL: str = "eleven_flash_v2_5"
    TTS_VOICE_FEMALE: str = "Hh0rE70WfnSFN80K8uJC"
    TTS_VOICE_MALE: str = "uFIXVu9mmnDZ7dTKCBTX"
    ELEVENLABS_API_KEY: str


class QuestionClassificationSettings(BaseSettings):
    """Settings for question classification service."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    QUESTION_CLASSIFICATION_MODEL: str = "shahrukhx01/question-vs-statement-classifier"
    QUESTION_CLASSIFICATION_CONFIDENCE_THRESHOLD: float = 0.7


class OpenAITTSSettings(BaseSettings):
    """Settings for OpenAI TTS service."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    TTS_MODEL: str = "gpt-4o-mini-tts"
    TTS_VOICE_FEMALE: str = "shimmer"
    TTS_VOICE_MALE: str = "verse"
    OPENAI_API_KEY: str


class BookingFlowSettings(BaseSettings):
    """Settings for intent classification service."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    BOOKING_FLOW_MODEL: str = "gpt-4.1"
    BOOKING_FLOW_PERSONA: BookingFlowPersona | None = None
    OPENAI_API_KEY: str

    TRIGGER_WORDS: list[str] = ["calendar", "verify", "check", "schedule"]

    def contains_trigger_word(self, message: str) -> bool:
        """Check if the message contains any of the trigger words (case-insensitive)."""
        message_lower = message.lower()
        return any(word.lower() in message_lower for word in self.TRIGGER_WORDS)


class RephraserSettings(BaseSettings):
    """Settings for rephraser service."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    REPHRASER_MODEL: str = "gpt-4o-2024-08-06"
    OPENAI_API_KEY: str


class TTSSettings(BaseSettings):
    """Settings for TTS provider selection."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    TTS_PROVIDER: str = "openai"


class StorageSettings(BaseSettings):
    """Settings for Azure Blob Storage."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    AZURE_STORAGE_CONNECTION_STRING: str
    AZURE_STORAGE_STATIC_CONTAINER_NAME_OAI: str = "static-recordings-oai"
    AZURE_STORAGE_STATIC_CONTAINER_NAME_11LABS: str = "static-recordings-11labs"
    AZURITE_PUBLIC_URL: str | None = None
    LOCAL_STORAGE_DYNAMIC_CONTAINER_NAME: str = "data/dynamic_recordings"


class CalendarSettings(BaseSettings):
    """Settings for Microsoft Dynamics 365 Web API."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DYNAMICS_ERP_BOOKING: bool = True
    DYNAMICS_API_URL: str | None = None
    DYNAMICS_TENANT_ID: str | None = None
    DYNAMICS_CLIENT_ID: str | None = None
    DYNAMICS_CLIENT_SECRET: str | None = None
    DYNAMICS_API_VERSION: str = "/api/data/v9.2"

    APPOINTMENT_DURATION_MINUTES: int = 60
    AVAILABILITY_LOOKAHEAD_DAYS: int = 30
    WORKING_HOURS_START: str = "09:00"
    WORKING_HOURS_END: str = "17:00"


class ApplicationSettings:
    """Main application settings container."""

    # TTS settings can be either ElevenLabs or OpenAI depending on provider set
    tts: ElevenLabsTTSSettings | OpenAITTSSettings

    def __init__(self) -> None:
        """Initializes the settings object by loading sub-configurations."""
        self.auth = AuthSettings()
        self.engine = EngineSettings()
        self.telephony = TelephonySettings()
        self.intent_classification = IntentClassificationSettings()
        self.question_classification = QuestionClassificationSettings()
        self.voicemail_detection = VoicemailDetectionSettings()
        self.booking_flow = BookingFlowSettings()
        self.conversation = ConversationSettings()

        # Initialize TTS settings based on provider
        tts_provider_settings = TTSSettings()
        if tts_provider_settings.TTS_PROVIDER.lower() == "elevenlabs":
            self.tts = ElevenLabsTTSSettings()
        else:
            self.tts = OpenAITTSSettings()

        self.storage = StorageSettings()
        self.rephraser = RephraserSettings()
        self.calendar = CalendarSettings()


settings = ApplicationSettings()
