cd /home/ubuntu/app/zeta-voice
source .venv/bin/activate
uv pip install -e .


source .env && uvicorn zeta_voice.main:app --host 0.0.0.0 --port 8000 --workers 1 --log-level info



required
uv pip install msal
