# Zeta Voice — EC2 Deployment Guide (No Docker, tmux)

> **Target**: Ubuntu 24.04 LTS on AWS EC2 (ARM or x86)
> **Stack**: Uvicorn + PostgreSQL + Nginx + **tmux** (no systemd, no Docker)
> **Storage**: AWS S3 (`voice-oai` / `voice-11labs` in `eu-central-1`)

---

## Table of Contents

1. [EC2 Instance Setup](#1-ec2-instance-setup)
2. [System Packages](#2-system-packages)
3. [PostgreSQL Database](#3-postgresql-database)
4. [Clone the Repository](#4-clone-the-repository)
5. [Python Environment & Dependencies](#5-python-environment--dependencies)
6. [Environment Variables (.env)](#6-environment-variables-env)
7. [Download ML Models](#7-download-ml-models)
8. [Create Runtime Directories](#8-create-runtime-directories)
9. [Configure Voices & Generate Audio](#9-configure-voices--generate-audio)
10. [Start Services with tmux](#10-start-services-with-tmux)
11. [Nginx Reverse Proxy](#11-nginx-reverse-proxy)
12. [HTTPS with Let's Encrypt (Recommended)](#12-https-with-lets-encrypt-recommended)
13. [AWS S3 Bucket Permissions](#13-aws-s3-bucket-permissions)
14. [Twilio Webhook Configuration](#14-twilio-webhook-configuration)
15. [Smoke Tests](#15-smoke-tests)
16. [Updating the App (Re-deploy)](#16-updating-the-app-re-deploy)
17. [tmux Quick Reference](#17-tmux-quick-reference)
18. [Troubleshooting](#18-troubleshooting)

---

## 1. EC2 Instance Setup

### Recommended Specs

| Resource | Minimum | Recommended |
|---|---|---|
| Instance type | `t3.medium` (2 vCPU, 4 GB) | `t3.large` (2 vCPU, 8 GB) |
| OS | Ubuntu 24.04 LTS | Ubuntu 24.04 LTS |
| Storage | 30 GB gp3 | 50 GB gp3 |
| Region | `eu-central-1` | `eu-central-1` |

### Security Group Rules (Inbound)

| Port | Protocol | Source | Purpose |
|---|---|---|---|
| 22 | TCP | Your IP | SSH |
| 80 | TCP | 0.0.0.0/0 | HTTP (Nginx) |
| 443 | TCP | 0.0.0.0/0 | HTTPS |

> Ports 8000 and 8001 should **not** be open to the internet — Nginx proxies them.

### IAM Role (Recommended — skip hardcoding AWS keys)

Attach an IAM Role to the EC2 instance with this policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject",
               "s3:ListBucket", "s3:CreateBucket", "s3:DeletePublicAccessBlock"],
    "Resource": [
      "arn:aws:s3:::voice-oai", "arn:aws:s3:::voice-oai/*",
      "arn:aws:s3:::voice-11labs", "arn:aws:s3:::voice-11labs/*"
    ]
  }]
}
```

With the IAM role attached, leave `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` blank in `.env`.

---

## 2. System Packages

```bash
sudo apt-get update && sudo apt-get upgrade -y

sudo apt-get install -y \
    git curl wget build-essential \
    postgresql postgresql-contrib \
    nginx tmux \
    python3.12 python3.12-dev python3.12-venv \
    ffmpeg libsndfile1

# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/env
echo 'source $HOME/.local/env' >> ~/.bashrc
```

---

## 3. PostgreSQL Database

```bash
sudo systemctl enable postgresql --now

sudo -u postgres psql <<'SQL'
CREATE USER zeta WITH PASSWORD 'your_strong_password';
CREATE DATABASE zeta_voice OWNER zeta;
GRANT ALL PRIVILEGES ON DATABASE zeta_voice TO zeta;
SQL
```

---

## 4. Clone the Repository

```bash
mkdir -p /home/ubuntu/app/zeta-voice && cd /home/ubuntu/app/zeta-voice

git clone git@github.com:rahul-opti/voice-ai-test.git .
```

> **SSH key**: Add your EC2 key to GitHub under Settings → SSH Keys.

---

## 5. Python Environment & Dependencies

```bash
cd /home/ubuntu/app/zeta-voice

# Create virtual environment with Python 3.12 (with pip seeded for spacy download)
uv venv --python 3.12 --seed .venv

# Install app, all dependencies, and required runtime modules
uv pip install --python .venv/bin/python -e .
uv pip install msal

# Verify
.venv/bin/python -c "import zeta_voice; print('✓ Package installed')"
```

---

## 6. Environment Variables (.env)

```bash
cp /home/ubuntu/app/zeta-voice/.env.example /home/ubuntu/app/zeta-voice/.env
nano /home/ubuntu/app/zeta-voice/.env
```

Fill in these values:

```bash
# ── Public URL ────────────────────────────────────────────────────────────────
BASE_URL="https://your-domain.com"    # or http://<EC2-public-IP> for initial testing

# ── Twilio ────────────────────────────────────────────────────────────────────
TWILIO_ACCOUNT_SID="ACxxxxxxxx..."
TWILIO_AUTH_TOKEN="your_token"
TWILIO_PHONE_NUMBERS=["+15551234567"]

# ── Database ──────────────────────────────────────────────────────────────────
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=zeta_voice
POSTGRES_USER=zeta
POSTGRES_PASSWORD=your_strong_password

# ── AI / LLM ──────────────────────────────────────────────────────────────────
OPENAI_API_KEY="sk-..."
ELEVENLABS_API_KEY="your_key"        # only if using ElevenLabs TTS

# ── AWS S3 ────────────────────────────────────────────────────────────────────
# Leave blank if using EC2 IAM Role (preferred)
AWS_ACCESS_KEY_ID=""
AWS_SECRET_ACCESS_KEY=""
AWS_REGION="eu-central-1"
AWS_S3_BUCKET_NAME_OAI="voice-oai"
AWS_S3_BUCKET_NAME_11LABS="voice-11labs"

# ── Security ──────────────────────────────────────────────────────────────────
ADMIN_API_KEY="generate-a-strong-random-key"
USER_API_KEY="generate-a-strong-random-key"
```

```bash
chmod 600 /home/ubuntu/app/zeta-voice/.env
```

---

## 7. Download ML Models

One-time downloads (~500 MB). Allow 5–15 minutes:

```bash
cd /home/ubuntu/app/zeta-voice

# spaCy NLP model
.venv/bin/python -m spacy download en_core_web_lg

# Question-vs-statement transformer model (cached to disk)
# Note: You can safely ignore any "UNEXPECTED" warnings about `bert.embeddings.position_ids` during download.
.venv/bin/python - <<'PY'
from transformers import AutoModelForSequenceClassification, AutoTokenizer
MODEL_ID = "shahrukhx01/question-vs-statement-classifier"
MODEL_DIR = "src/zeta_voice/question_classification/model"
AutoTokenizer.from_pretrained(MODEL_ID, cache_dir=MODEL_DIR)
AutoModelForSequenceClassification.from_pretrained(MODEL_ID, cache_dir=MODEL_DIR)
print("✓ Model ready")
PY
```

---

## 8. Create Runtime Directories

```bash
mkdir -p /home/ubuntu/app/zeta-voice/data/dynamic_recordings
mkdir -p /home/ubuntu/app/zeta-voice/data/static_recordings
mkdir -p /home/ubuntu/app/zeta-voice/logs
```

---

## 9. Configure Voices & Generate Audio

Before starting the app, generate your static chatbot audio files for ElevenLabs:

1. **Add your Voice IDs** to `config/elevenlabs_voices.json`.
2. **Add Custom Voice Tuning**: Create a base tuning file (e.g. `config/elevenlabs_voice_settings/Eve.json`) and a fillers tuning file (`config/elevenlabs_voice_settings/Eve_fillers.json`) for your new voice to configure stability, speed, and style.
3. **Generate Audio**: Run the script for each installed voice:
   ```bash
   cd /home/ubuntu/app/zeta-voice
   uv run scripts/generate_all_recordings.py --voice-name Eve
   ```
4. **Sync to S3**: Upload the generated `.wav` files directly to AWS:
   ```bash
   aws s3 sync data/static_recordings/ s3://voice-11labs/ --acl public-read
   ```

---

## 10. Start Services with tmux

This project uses **tmux** to run both services in persistent background sessions.

### Start (first time or after a reboot)

```bash
cd /home/ubuntu/app/zeta-voice
bash deploy/tmux-start.sh
```

This creates a tmux session called **`zeta-voice`** with 3 windows:

| Window | Name | What runs |
|---|---|---|
| 0 | `zeta-app` | Main voice AI app — port **8000** |
| 1 | `zeta-admin` | Admin app — port **8001** |
| 2 | `logs` | Live tail of both log files |

### Attach to a running session

```bash
tmux attach -t zeta-voice
```

### Stop all services

```bash
bash deploy/tmux-stop.sh
```

### Restart all services

```bash
bash deploy/tmux-restart.sh
```

### Auto-start on EC2 reboot (via crontab)

```bash
crontab -e
# Add this line:
@reboot sleep 15 && cd /home/ubuntu/app/zeta-voice && bash deploy/tmux-start.sh >> /home/ubuntu/app/zeta-voice/logs/boot.log 2>&1
```

---

## 11. Nginx Reverse Proxy

```bash
mkdir -p /home/ubuntu/nginx
cp /home/ubuntu/app/zeta-voice/deploy/nginx.conf /home/ubuntu/nginx/zeta-voice.conf

# Set your domain
nano /home/ubuntu/nginx/zeta-voice.conf
# Change:  server_name _;
# To:      server_name your-domain.com;

sudo ln -sf /home/ubuntu/nginx/zeta-voice.conf /etc/nginx/sites-enabled/zeta-voice
sudo rm -f /etc/nginx/sites-enabled/default

sudo nginx -t && sudo systemctl reload nginx && sudo systemctl enable nginx
```

Test: `curl http://<your-ec2-public-ip>/` — you should get a JSON response.

---

## 12. HTTPS with Let's Encrypt (Recommended)

Twilio requires HTTPS in production.

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
sudo systemctl enable certbot.timer
```

---

## 13. AWS S3 Bucket Permissions

Your buckets must allow public read so Twilio can fetch audio. Run from your local machine or the EC2 instance (with `awscli` installed):

```bash
for BUCKET in voice-oai voice-11labs; do
  aws s3api put-public-access-block \
    --bucket "$BUCKET" --region eu-central-1 \
    --public-access-block-configuration \
      "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false"

  aws s3api put-bucket-policy --bucket "$BUCKET" --region eu-central-1 --policy "{
    \"Version\":\"2012-10-17\",
    \"Statement\":[{\"Effect\":\"Allow\",\"Principal\":\"*\",
      \"Action\":\"s3:GetObject\",
      \"Resource\":\"arn:aws:s3:::$BUCKET/*\"}]}"

  echo "✓ $BUCKET configured"
done
```

---

## 14. Twilio Webhook Configuration

In **Twilio Console → Phone Numbers → your number → Voice**:

- **"A call comes in"**: `https://your-domain.com/twilio/voice`
- **HTTP Method**: `POST`

`BASE_URL` in `.env` must exactly match this domain (with `https://`).

---

## 15. Smoke Tests

```bash
# Are tmux windows running?
tmux list-windows -t zeta-voice

# Health check via localhost
curl -s http://localhost:8000/health

# Health check via public URL
curl -s https://your-domain.com/health

# S3 connectivity
cd /home/ubuntu/app/zeta-voice && .venv/bin/python - <<'PY'
import boto3
s3 = boto3.client("s3", region_name="eu-central-1")
buckets = [b["Name"] for b in s3.list_buckets()["Buckets"]]
print("S3 buckets visible:", buckets)
PY
```

---

## 16. Updating the App (Re-deploy)

```bash
cd /home/ubuntu/app/zeta-voice
git pull origin main
uv pip install --python .venv/bin/python -e .   # only needed if deps changed
bash deploy/tmux-restart.sh
```

Or use the deploy script (handles everything):

```bash
sudo bash deploy/deploy.sh
```

---

## 17. tmux Quick Reference

| Action | Command |
|---|---|
| Attach to session | `tmux attach -t zeta-voice` |
| Detach (keep running) | `Ctrl+b` then `d` |
| Switch to window 0 | `Ctrl+b` then `0` |
| Switch to window 1 | `Ctrl+b` then `1` |
| Switch to window 2 (logs) | `Ctrl+b` then `2` |
| Scroll up in window | `Ctrl+b` then `[` (then arrows; `q` to exit) |
| Kill current window | `Ctrl+b` then `&` |
| List all sessions | `tmux ls` |
| New window | `Ctrl+b` then `c` |
| Rename window | `Ctrl+b` then `,` |

---

## 18. Troubleshooting

| Symptom | Action |
|---|---|
| Services not running after reboot | `bash deploy/tmux-start.sh` (or check crontab @reboot entry) |
| Window 0/1 exited immediately | `tmux attach -t zeta-voice` → switch to dead window → scroll up to see error |
| `ModuleNotFoundError: zeta_voice` | `uv pip install --python .venv/bin/python -e .` |
| `AWS credentials not found` | Set keys in `.env` or attach IAM Role to EC2 instance |
| `S3 upload fails (Access Denied)` | Re-run bucket policy commands in [Step 13](#13-aws-s3-bucket-permissions) |
| 502 Bad Gateway | Uvicorn crashed — attach to session and check `logs/app.log` |
| Twilio "Invalid application" | Ensure `BASE_URL` in `.env` matches your HTTPS domain exactly |
| Port 8000 not reachable externally | Expected — EC2 SG should block 8000/8001; use Nginx on port 80/443 |

### Useful One-Liners

```bash
# View last 100 lines of app log
tail -100 /home/ubuntu/app/zeta-voice/logs/app.log

# Attach and go straight to logs window
tmux attach -t zeta-voice \; select-window -t logs

# Run a one-off script inside the venv
cd /home/ubuntu/app/zeta-voice && .venv/bin/python scripts/generate_all_recordings.py

# Check what's listening on which port
sudo ss -tlpn | grep -E '8000|8001|80|443'

# Run the app directly in the foreground (without tmux)
cd /home/ubuntu/app/zeta-voice
source .env && .venv/bin/python -m uvicorn zeta_voice.main:app --host 0.0.0.0 --port 8000 --workers 1 --log-level info
```
