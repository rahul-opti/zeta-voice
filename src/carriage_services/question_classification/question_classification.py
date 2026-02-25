from pathlib import Path

import torch
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
)

from carriage_services.paths import QUESTION_CLASSIFICATION_MODEL_PATH
from carriage_services.settings import settings

MODEL_ID = settings.question_classification.QUESTION_CLASSIFICATION_MODEL
LOCAL_DIR = Path(QUESTION_CLASSIFICATION_MODEL_PATH)


def download_model_files() -> None:
    """Download model and tokenizer files to the local directory."""
    target_dir = Path(LOCAL_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    _ = AutoTokenizer.from_pretrained(MODEL_ID, cache_dir=str(target_dir))
    _ = AutoModelForSequenceClassification.from_pretrained(MODEL_ID, cache_dir=str(target_dir))


class QuestionClassification:
    """A class for classifying whether given text is a question using locally stored model."""

    def __init__(self, model_id: str = MODEL_ID, local_dir: Path | str = LOCAL_DIR) -> None:
        self._model_id = model_id
        self._local_dir = Path(local_dir)

        if not self._local_dir.exists() or not any(self._local_dir.iterdir()):
            download_model_files()

        self._tokenizer, self._model = self._load_model()
        self._model.eval()

    def _load_model(self) -> tuple[AutoTokenizer, AutoModelForSequenceClassification]:
        """Load tokenizer and model weights.

        Returns:
            Tuple[AutoTokenizer, AutoModelForSequenceClassification]: The loaded tokenizer and model.

        Raises:
            RuntimeError: If the model files are not available.
        """
        try:
            tokenizer = AutoTokenizer.from_pretrained(
                self._model_id, cache_dir=str(self._local_dir), local_files_only=True
            )
            model = AutoModelForSequenceClassification.from_pretrained(
                self._model_id, cache_dir=str(self._local_dir), local_files_only=True
            )
        except OSError as exc:
            raise RuntimeError(
                "Model files not found locally. Ensure the model is present in " f"'{self._local_dir}'."
            ) from exc
        return tokenizer, model

    def classify(self, text: str) -> tuple[bool, float]:
        """Classify input text as question or statement.

        Args:
            text (str): Input text to classify.

        Returns:
            Tuple[bool, float]: True if question, False if statement, and confidence score in [0.0, 1.0].
        """
        inputs = self._tokenizer([text], padding=True, truncation=True, return_tensors="pt")
        with torch.no_grad():
            outputs = self._model(**inputs)
            probs = torch.softmax(outputs.logits, dim=-1).squeeze(0)
        label_idx = int(torch.argmax(probs).item())
        is_question = label_idx == 1
        confidence = float(probs[label_idx].item())
        return is_question, confidence
