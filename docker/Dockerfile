FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install -y curl gettext-base python3-pip && apt-get clean
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

COPY pyproject.toml README.md LICENSE.md ./

COPY config/ /usr/local/lib/python3.12/config/
COPY src/ ./src/
COPY data/ ./data/

# This is an interim solution until we are using blob storage
RUN mkdir -p /app/data/dynamic_recordings /app/data/static_recordings
RUN uv pip install --system .
RUN python -m spacy download en_core_web_lg
RUN python -c "\
from transformers import AutoModelForSequenceClassification, AutoTokenizer; \
MODEL_ID = 'shahrukhx01/question-vs-statement-classifier'; \
MODEL_DIR = '/app/src/carriage_services/question_classification/model'; \
print(f'Downloading model {MODEL_ID} to {MODEL_DIR}...'); \
_ = AutoTokenizer.from_pretrained(MODEL_ID, cache_dir=MODEL_DIR); \
_ = AutoModelForSequenceClassification.from_pretrained(MODEL_ID, cache_dir=MODEL_DIR)"

EXPOSE 8000

CMD ["uvicorn", "carriage_services.main:app", "--host", "0.0.0.0", "--port", "8000"]
