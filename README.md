# Carriage Services - Telephony Chatbot

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE.md)
[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-supported-blue.svg)](https://www.docker.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.116.1-green.svg)](https://fastapi.tiangolo.com/)
[![Twilio](https://img.shields.io/badge/Twilio-9.7.0-red.svg)](https://www.twilio.com/)
[![OpenAI](https://img.shields.io/badge/OpenAI-1.97.1-purple.svg)](https://openai.com/)
[![ElevenLabs](https://img.shields.io/badge/ElevenLabs-2.14.0-orange.svg)](https://elevenlabs.io/)
[![Azure](https://img.shields.io/badge/Azure-Container%20Apps-blue.svg)](https://azure.microsoft.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-blue.svg)](https://www.postgresql.org/)
[![GitLab CI/CD](https://img.shields.io/badge/GitLab-CI%2FCD-orange.svg)](https://docs.gitlab.com/ee/ci/)
[![Terraform](https://img.shields.io/badge/Terraform-Azure-purple.svg)](https://www.terraform.io/)

The goal of this project is to create a Voice AI Agent making outbound calls to potential leads.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Telephony](#telephony)
  - [Local Execution](#local-execution)
  - [Autonomous Deployment](#autonomous-deployment-gitlab-cicd-to-azure)
- [Deployment (Azure Terraform)](#deployment-azure-terraform)
- [Usage](#usage)
- [Recording and Saving Chatbot Responses](#recording-and-saving-chatbot-responses-from-csv-file)
- [Data Export](#data-export)
- [Terminal Conversation](#terminal-conversation)
- [Twilio Recordings Download Script](#twilio-recordings-download-script)
- [Appendix A: Service Principal Permissions](#appendix-a-service-principal-permissions-json)

## Prerequisites

- Python 3.12+
- Docker and Docker Compose
- A Twilio account with an active phone number
- `ngrok` or another tunneling service to expose your local server
- OpenAI account with API access for AI services (intent classification, voicemail detection, booking flow, and optional TTS)
- ElevenLabs account with API access for TTS services (if using ElevenLabs TTS provider)
- Azure account for cloud deployment and blob storage
- Microsoft Dynamics 365 account (optional) for calendar/booking integration

## Installation

1. **Install project and dependencies:**

   ```bash
   make install
   ```

   This creates a virtual environment and installs required packages.

2. **Install development tools (optional):**

   ```bash
   make install-dev
   ```

   This installs pre-commit hooks for code quality.

3. **Run neutralize_phrases test (optional):**

   The neutralize_phrases test validates that forbidden phrases are properly replaced in booking flow responses. It's optional and disabled by default to avoid unnecessary API costs during installation.

   To enable the test, set the `RUN_NEUTRALIZE_TEST` environment variable:

   ```bash
   RUN_NEUTRALIZE_TEST=true make install
   # or
   RUN_NEUTRALIZE_TEST=true make install-dev
   ```

4. **Activate virtual environment:**

   ```bash
   source .venv/bin/activate
   ```

## Configuration

1. **Environment Variables:**
   - Copy the example environment file: `cp .env.example .env`
   - Edit `.env` with your credentials and API keys.

   See `.env.example` for a complete list of required environment variables and their descriptions.

2. **Voice Configuration (ElevenLabs):**
   The available TTS voices are configured in `config/elevenlabs_voices.json`. Each voice entry includes:
   - `id`: The ElevenLabs voice ID
   - `name`: The display name used in the API and for the bot's self-introduction

   Example configuration:

   ```json
   {
     "voices": [
       { "id": "Hh0rE70WfnSFN80K8uJC", "name": "Maria" },
       { "id": "uFIXVu9mmnDZ7dTKCBTX", "name": "Alex" },
       { "id": "RNnkVeW25AwKYxZgnHBH", "name": "Luke" }
     ]
   }
   ```

   Each voice should have corresponding voice settings files in `config/elevenlabs_voice_settings/`:
   - `<VoiceName>.json` - Regular voice settings
   - `<VoiceName>_fillers.json` - Voice settings for filler words

## Dynamics 365 Integration Setup

To enable appointment booking with Microsoft Dynamics 365, the application requires an Azure AD App Registration (Service Principal) that is authorized to interact with your Dynamics 365 environment.

### 1. Create an Azure AD App Registration

1.  Navigate to **Azure Active Directory** in the Azure Portal.
2.  Go to **App registrations** and click **+ New registration**.
3.  Give it a descriptive name (e.g., `CarriageServicesVoiceAI`).
4.  Select "Accounts in this organizational directory only".
5.  Click **Register**.
6.  From the **Overview** page, copy the **Application (client) ID** and **Directory (tenant) ID**. These are your `DYNAMICS_CLIENT_ID` and `DYNAMICS_TENANT_ID`.
7.  Go to **Certificates & secrets**, click **+ New client secret**, give it a description, and copy the **Value**. This is your `DYNAMICS_CLIENT_SECRET`.

### 2. Create an Application User in Power Platform

The App Registration must be linked to an Application User within your Dynamics 365 environment.

1.  Navigate to the [Power Platform Admin Center](https://admin.powerplatform.microsoft.com).
2.  Select **Environments** and choose the target Dynamics 365 environment.
3.  Go to **Settings > Users + permissions > Application users**.
4.  Click **+ New app user**.
5.  In the side panel, click **+ Add an app**.
6.  Paste the **Application (client) ID** from step 1.6 into the search bar, select your app, and click **Add**.
7.  Select a **Business Unit** (typically the root business unit).
8.  Click the pencil icon next to **Security roles** and assign a role. You may need to create a custom role. Click **Save** and then **Create**.

### 3. Configure Security Role Permissions

The Application User's security role must have the minimum required permissions to read lead data and create appointments.

1.  In the Power Platform Admin Center, go to **Settings > Users + permissions > Security roles**.
2.  Find and open the role you assigned to the Application User.
3.  Grant the following privileges at the **Business Unit** level (half-filled green circle) or **Organization** level (full green circle):
    *   **activitypointer**: `Create`, `Read`, `Write`, `Append`, `Append To`
    *   **annotation**: `Create`, `Read`, `Write`, `Append`, `Append To`
    *   **systemuser**: `Read`, `Append To`
    *   **lead**: `Read`
4.  **Save and Close** the security role. The changes may take a few minutes to apply.

### 4. Update `.env` File

Ensure the following variables are correctly set in your `.env` file:

```dotenv
# Set to "true" to enable the Dynamics 365 integration for booking
DYNAMICS_ERP_BOOKING=True
DYNAMICS_API_URL="https://your-org.crm.dynamics.com/"
DYNAMICS_TENANT_ID="<Your-Directory-Tenant-ID>"
DYNAMICS_CLIENT_ID="<Your-Application-Client-ID>"
DYNAMICS_CLIENT_SECRET="<Your-Client-Secret-Value>"
DYNAMICS_API_VERSION="/api/data/v9.2"
```



## Telephony

### Local Execution

#### Execution with Docker Compose (Recommended)

This method starts the application along with its PostgreSQL and **Azurite (Azure Storage Emulator)** dependencies.

1. **Expose Local Server:**
    Start `ngrok` to create a public URL that forwards to your local port 8000.

    ```bash
    ngrok http 8000
    ```

2. **Update `.env`:**
    Set `BASE_URL` in your `.env` file to the `https` forwarding URL provided by ngrok. The `AZURE_STORAGE_CONNECTION_STRING` is pre-configured for the local Azurite container.

3. **Build and Run Containers:**

    ```bash
    docker compose up --build -d
    ```

    The application will be running and accessible via the ngrok URL. To view logs, run `docker compose logs -f app`.

**Note on Using Live Azure Storage for Local Development:**

The default Docker Compose setup uses **Azurite**, a local Azure Storage emulator. This is sufficient for most development. However, if you need Twilio or other external services to access recordings, you must use a publicly accessible Azure Storage account.

To use the deployed Azure Storage account for local development:

1. **Get the Connection String:** Obtain the connection string for the storage account from your deployed environment (e.g., from the Azure Portal or Terraform outputs).
2. **Update `.env`:** Replace the value of `AZURE_STORAGE_CONNECTION_STRING` in your `.env` file with the connection string.
3. **Create and Configure a Development Container:**
    - In the Azure Portal, navigate to the storage account.
    - Create a new blob container (e.g., `dev-static-recordings-yourname`).
    - Update the `AZURE_STORAGE_STATIC_CONTAINER_NAME_OAI` and `AZURE_STORAGE_STATIC_CONTAINER_NAME_11LABS` variable in your `.env` file with the names of your new containers.
4. **Restart Docker:** Run `docker compose down && docker compose up -d`. Your local application will now use the live Azure storage account for static recordings.

**Note:**

To completely reset the local environment, including the database data, run:

```bash
docker compose down -v
```

#### Local Execution (Without Docker)

This method is for running the application directly on your host machine. It requires you to have PostgreSQL or SQLite running and accessible separately.

1. **Expose Local Server:**
    Start `ngrok` to create a public URL for your local server on port 8000.

    ```bash
    ngrok http 8000
    ```

2. **Run Dependencies:**
    Start PostgreSQL. You can use Docker for this:

    ```bash
    # Run PostgreSQL
    docker run -d --name postgres -p 5432:5432 -e POSTGRES_PASSWORD=mysecretpassword -e POSTGRES_USER=user -e POSTGRES_DB=mydb postgres:16-alpine
    ```

3. **Update `.env`:**
    - Set `BASE_URL` to the `ngrok` forwarding URL.
    - Update `DB_PATH` to your PostgreSQL connection URL (e.g., `postgresql+psycopg://user:mysecretpassword@localhost:5432/mydb`).

4. **Run Server:**

    ```bash
    make run
    ```

    The server will run on `http://127.0.0.1:8000`.

## Autonomous Deployment (GitLab CI/CD to Azure)

The project is configured for autonomous deployment to Azure via GitLab CI/CD whenever changes are pushed to the `main` branch. The pipeline automates provisioning, building, and deploying the application.

### GitLab CI/CD Prerequisites

1. **GitLab Runner**: A GitLab runner with the tag `all-ds` must be available and configured for the project.
2. **Custom Docker Image**: The CI/CD pipeline relies on a custom Docker image (`registry.gitlab.com/deepsense.ai/g-axia-ai/carriage-services/terraformazuredocker:0.0.1`) that contains both the Azure CLI and Terraform CLI. This image must be built and pushed to a registry accessible by the GitLab runner. The `docker/Dockerfile.terraform` file is provided for this purpose.

    **Building the `terraformazuredocker` Image:**

    ```bash
    # Navigate to the project root
    docker build -f docker/Dockerfile.terraform -t <your-gitlab-registry>/terraformazuredocker:0.0.1 .
    docker push <your-gitlab-registry>/terraformazuredocker:0.0.1
    ```

    Update the `.gitlab-ci.yml` file to point to your image's location if it differs from the one in the file.

3. **Terraform State Backend**: A Terraform state backend (e.g., Azure Storage Account, AWS S3, or GitLab's built-in state management) must be provisioned and configured. This backend stores the Terraform state file and must be accessible by the GitLab runner. The current `tf/main.tf` configuration uses an Azure Storage Account for this purpose. This setup is independent of the application deployment itself.

    **Note**: Ensure the Azure Service Principal (`ARM_CLIENT_ID`) used by GitLab CI/CD has the necessary permissions (e.g., "Storage Blob Data Contributor") on the state backend storage account.

4. **GitLab CI/CD Variables**:  Configure the required CI/CD variables in your GitLab project's settings (`Settings > CI/CD > Variables`). Example core variables include:
   - `ARM_CLIENT_ID`, `ARM_CLIENT_SECRET`, `ARM_TENANT_ID`, `ARM_SUBSCRIPTION_ID`: Azure Service Principal credentials
   - `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBERS`: Twilio credentials
   - `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`: AI service API keys
   - `ADMIN_API_KEY`, `USER_API_KEY`: Application API keys

   > **Note:** For the complete list of all required variables, please contact the responsible `deepsense.ai` dev team.

### Pipeline Overview

The `.gitlab-ci.yml` defines the following stages that run automatically on commits to `main`:

1. `lint`: Checks code formatting and quality using `ruff` and `pre-commit`.
2. `tests`: Runs the `pytest` test suite.
3. `provision_acr`: Uses Terraform to provision an Azure Container Registry (ACR).
4. `build_image`: Builds the application's Docker image and pushes it to the newly created ACR.
5. `deploy_services`: Uses Terraform to deploy all other Azure resources, including the Container App which uses the image from the ACR.

### Manual Jobs

- `promptfoo_tests`: This job runs prompt evaluation tests using `promptfoo`. It is a manual job that can be triggered from the GitLab pipeline UI on the `main` branch. It generates and saves test reports as artifacts.

## Deployment (Azure Terraform)

This project can be deployed to Azure using Terraform. The Terraform configuration provisions Azure Container Apps, PostgreSQL Flexible Server, and Azure Key Vault.

### Terraform Deployment Prerequisites

- **Azure CLI:** Ensure you have the Azure CLI installed and configured. Authenticate using `az login`.
- **Terraform CLI:** Install Terraform CLI.
- **Azure Subscription:** An active Azure subscription.
- **Azure Service Principal:** A Service Principal with the permissions in Appendix A

### Terraform Configuration

1. **Navigate to the Terraform directory:**

    ```bash
    cd tf
    ```

2. **Create a `terraform.tfvars` file:**
   Copy the example and populate it with your specific values. This file holds sensitive information and should not be committed to version control.

   ```bash
   cp terraform.tfvars.example terraform.tfvars
   ```

   Edit `terraform.tfvars`; example essential variables include:
   - `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBERS`: Your Twilio credentials
   - `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`: Your AI service API keys
   - `ADMIN_API_KEY`, `USER_API_KEY`: Application API keys
   - `subscription_id`: Your Azure subscription ID

   > **Note:** For detailed configuration guidance and the complete list of required variables, please contact the responsible `deepsense.ai` dev team.

### Initialization

Initialize the Terraform working directory to download necessary provider plugins:

```bash
terraform init
```

### Deployment

Apply the Terraform configuration to provision resources in Azure. Review the plan carefully before confirming.

```bash
terraform apply
```

Type `yes` when prompted to confirm the deployment.

### Outputs

After successful deployment, Terraform will output important information, including the public URL of your Container App.

```bash
terraform output container_app_url
```

Use this URL to update the `BASE_URL` in your `.env` file (or directly in Key Vault if you are managing secrets manually).

### Database Compatibility

The application is designed to work with both **PostgreSQL** and **SQLite**.

- **PostgreSQL:** When deployed with Terraform, a PostgreSQL Flexible Server is provisioned. The application will automatically connect to it using the `DB_PATH` environment variable set from Key Vault (`DB_CONNECTION_STRING`).
- **SQLite:** For local development without Docker Compose, you can configure `DB_PATH` in your `.env` file to point to a local SQLite file (e.g., `data/carriage.db`). The application will detect the `sqlite+pysqlite:///` prefix and use the SQLite driver.

## Usage

### Authentication

The application uses API key authentication with two levels of access:

- **User API Key**: Required for call initiation and status monitoring endpoints
- **Admin API Key**: Required for data export and system administration endpoints

Include the appropriate API key in the `X-API-Key` header for all authenticated requests.

### Starting a Call

Send a POST request to the `/start_call` endpoint to initiate a call.

For detailed information on the request body parameters, including their types, descriptions, and required status, please refer to the **Swagger UI documentation** for this endpoint. Navigate to the `/start_call` endpoint and inspect the **"Schema" tab** within the "Request body" section. This will provide you with an up-to-date view of all available parameters.

**Example:**

```bash
curl -X POST "http://127.0.0.1:8000/start_call?voice_name=Maria?from_number=%2B15551234567" \
-H "Content-Type: application/json" \
-H "X-API-Key: your_user_api_key" \
-d '{
    "to_number": "+15558675309",
    "user_id": "lead-42",
    "handoff_number": "+15551112222"
}'
```

The `from_number` query parameter is optional and specifies which Twilio phone number to use for the outbound call. If omitted, the first number from `TWILIO_PHONE_NUMBERS` is used. Available numbers appear as a dropdown in the Swagger UI.

### Monitoring System Status

Check the status of active conversation runners:

```bash
curl -X GET "http://127.0.0.1:8000/runners" \
-H "X-API-Key: your_user_api_key"
```

## Recording and saving chatbot responses from csv file

**Prerequisites for silence removal**: If you plan to use the silence removal feature, you must install `ffmpeg`:

```bash
sudo apt install -y ffmpeg
```

In order to record and save predefined chatbot responses from csv file you need to run the following script:

```bash
uv run ./scripts/save_chatbot_response_recordings.py config/conversation_config/slots_with_responses.csv slot_name filler_word_1,filler_word_2,filler_word_3,filler_word_4,filler_word_5,intro_chatbot_response,example_chatbot_response_1,example_chatbot_response_2,example_chatbot_response_3,example_chatbot_response_4,example_chatbot_response_5 Maria
```

### Parameters

- **CSV file path**: Path to the CSV file containing chatbot responses (e.g., `config/conversation_config/slots_with_responses.csv`)
- **Intent name column**: Column name that contains the response ID (e.g., `slot_name`)
- **Response columns**: Comma-separated list of column names containing response texts (e.g., `filler_word_1,filler_word_2,filler_word_3,filler_word_4,filler_word_5,intro_chatbot_response,example_chatbot_response_1,example_chatbot_response_2,example_chatbot_response_3,example_chatbot_response_4,example_chatbot_response_5`)
- **Voice name**: Name of the voice to use for TTS generation. Must match a voice name configured in `config/elevenlabs_voices.json` (e.g., `Maria`, `Alex`, `Luke`)

### Silence Removal Option

By default, the script removes silence from generated audio recordings to create cleaner, more natural-sounding speech. You can control this behavior using the `--remove-silence` flag:

```bash
# Remove silence (default behavior)
uv run ./scripts/save_chatbot_response_recordings.py config/conversation_config/slots_with_responses.csv slot_name intro_chatbot_response Maria --remove-silence

# Keep original audio with silence
uv run ./scripts/save_chatbot_response_recordings.py config/conversation_config/slots_with_responses.csv slot_name intro_chatbot_response Maria --no-remove-silence
```

The silence removal feature helps create more professional-sounding recordings by eliminating unnecessary pauses and dead air from the generated speech.

### Filler Generation Options

You can control whether to include or exclude generation of filler words (`filler_word_*`) using the following flags:

```bash
# Skip filler columns
uv run ./scripts/save_chatbot_response_recordings.py \
  config/conversation_config/slots_with_responses.csv \
  slot_name \
  filler_word_1,filler_word_2,filler_word_3,filler_word_4,filler_word_5,intro_chatbot_response,example_chatbot_response_1,example_chatbot_response_2,example_chatbot_response_3,example_chatbot_response_4,example_chatbot_response_5 \
  Maria \
  --skip-fillers

# Generate only filler columns
uv run ./scripts/save_chatbot_response_recordings.py \
  config/conversation_config/slots_with_responses.csv \
  slot_name \
  filler_word_1,filler_word_2,filler_word_3,filler_word_4,filler_word_5,intro_chatbot_response,example_chatbot_response_1,example_chatbot_response_2,example_chatbot_response_3,example_chatbot_response_4,example_chatbot_response_5 \
  Maria \
  --only-fillers
```

Note: Only `slots_with_responses.csv` contains `filler_word_*` columns. For other CSVs, `--skip-fillers` has no effect and `--only-fillers` results in no outputs.

### Batch Generation of All Recordings

For convenience, you can generate all predefined chatbot response recordings at once using the batch script:

```bash
# Generate all recordings with silence removal (default)
uv run scripts/generate_all_recordings.py

# Generate all recordings without silence removal
uv run scripts/generate_all_recordings.py --no-remove-silence
```

You can also control filler generation in batch mode:

```bash
# Skip filler_word_* columns across all batches
uv run scripts/generate_all_recordings.py --skip-fillers

# Generate only filler_word_* columns from slots_with_responses.csv
uv run scripts/generate_all_recordings.py --only-fillers
```

To generate recordings for a specific voice only:

```bash
# Generate recordings for Luke only
uv run scripts/generate_all_recordings.py --voice-name Luke
```

This script automatically processes all conversation configuration files:

- `slots_with_responses.csv`
- `faqs_with_responses.csv`
- `objections_with_responses.csv`
- `repetition_with_responses.csv`

It generates recordings for all voices configured in `config/elevenlabs_voices.json` (e.g., Maria, Alex, Luke), creating a complete set of TTS recordings for the entire conversation system.

### Local Recording Generation

If you want to preview audio quality before pushing to cloud storage, you can generate recordings directly to your filesystem using the local versions of the scripts. These mirror the `save_chatbot_response_recordings.py` and `generate_all_recordings.py` scripts in logic, and preserve the same cloud structure under a local directory.

Single CSV locally:

```bash
uv run ./scripts/save_chatbot_response_recordings_locally.py \
  config/conversation_config/slots_with_responses.csv \
  slot_name \
  filler_word_1,filler_word_2,filler_word_3,filler_word_4,filler_word_5,intro_chatbot_response,example_chatbot_response_1,example_chatbot_response_2,example_chatbot_response_3,example_chatbot_response_4,example_chatbot_response_5 \
  Maria \
  --save-recordings-to data/local_recordings \
  --no-remove-silence
```

Batch for all CSVs locally:

```bash
uv run ./scripts/generate_all_recordings_locally.py --save-recordings-to data/local_recordings --no-remove-silence
```

To generate local recordings for a specific voice only:

```bash
uv run ./scripts/generate_all_recordings_locally.py --voice-name Luke --save-recordings-to data/local_recordings
```

Filler options for local batch generation:

```bash
# Skip filler_word_* columns
uv run ./scripts/generate_all_recordings_locally.py --skip-fillers

# Generate only filler_word_* columns
uv run ./scripts/generate_all_recordings_locally.py --only-fillers

# Combine with other options as needed
uv run ./scripts/generate_all_recordings_locally.py --only-fillers --no-remove-silence --save-recordings-to data/local_recordings
```

Notes:

- TTS configuration, options and defaults (e.g., `--remove-silence`, `--max-concurrent`) mirror the scripts described above; refer to those subsections for details.

#### Single recording

For quick previews and quality checks of a single utterance, you can synthesize it to a local audio file (same mirroring as above):

```bash
uv run ./scripts/generate_single_recording.py \
  --utterance "Some text to be generated." \
  --voice-name Maria \
  --save-to data/single_recording/output.mp3 \
  --no-remove-silence
```

## Data Export

The application includes a separate admin service for exporting data from the database to CSV files. This service runs
on a different port to keep it isolated from the main telephony webhooks and requires admin-level authentication.

### Running the Admin Service

To start the admin server, run the following command from the project root after activating the virtual environment:

```bash
uvicorn carriage_services.main:admin_app --host 127.0.0.1 --port 8001
```

Or using the make command:

```bash
make admin
```

### Exporting Data

Once the admin server is running, you can export the `conversations`, `logs` and `errors` tables using a GET request with admin authentication.

**Example using `curl`:**

```bash
# Export the conversations table
curl -H "X-API-Key: your_admin_api_key" http://127.0.0.1:8001/export/conversations -o conversations.csv

# Export the logs table
curl -H "X-API-Key: your_admin_api_key" http://127.0.0.1:8001/export/logs -o logs.csv

# Export the errors table
curl -H "X-API-Key: your_admin_api_key" http://127.0.0.1:8001/export/errors -o errors.csv
```

### Conversation Status and Logs

The admin service also provides endpoints to check conversation status and retrieve logs:

```bash
# Get conversation status for a user
curl -H "X-API-Key: your_admin_api_key" http://127.0.0.1:8001/conversation/status/{user_id}

# Get latest conversation status for a user
curl -H "X-API-Key: your_admin_api_key" http://127.0.0.1:8001/conversation/status/latest/{user_id}

# Get logs for latest conversation of a user
curl -H "X-API-Key: your_admin_api_key" http://127.0.0.1:8001/conversation/logs/latest/{user_id}

# Get logs for a specific conversation
curl -H "X-API-Key: your_admin_api_key" http://127.0.0.1:8001/conversation/logs/{conversation_id}
```

The data will be downloaded and saved to the specified output files (`conversations.csv`, `logs.csv` and `errors.csv`).

## Terminal Conversation

For testing and development purposes, you can run text-based conversations directly in the terminal without using
telephony services. This allows you to interact with the conversation engine through command line input/output.

```bash
uv run ./scripts/run_terminal_conversation.py
```

You can run terminal conversation in 2 modes: text and url.

1. Bot responses returned in text form in terminal

```bash
uv run ./scripts/run_terminal_conversation.py --output-type=TEXT
```

2. URLs to recorded bot responses returned in terminal

```bash
uv run ./scripts/run_terminal_conversation.py --output-type=URL
```

Url mode requires running ngrok, for example:

```bash
ngrok http 8000
```

Then the env variable DYNAMIC_RECORDINGS_DIR has to be set to the folder where you want to store dynamic recordings and BASE_URL
has to be set to the URL returned by ngrok (STATIC_RECORDINGS_DIR can be left as a dummy variable for now as it is not
used).

## Twilio Recordings Download Script

Download call recordings from Twilio by phone number or specific call SID.

### Script Usage

The script supports two modes:

#### Download all recordings for a phone number

```bash
uv run scripts/download_twilio_recordings.py --outbound-number +1234567890
```

#### Download recordings for a specific call

```bash
uv run scripts/download_twilio_recordings.py --call-sid CAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Output

Recordings are automatically saved to:

```text
data/call_recordings/{number}/
```

Files are named with the format:

```text
{YYYYMMDD_HHMMSS}_{call_sid}_{recording_sid}.wav
```

## Appendix A: Service Principal Permissions JSON

```json
{
    ...,
    "properties": {
        ...
        "permissions": [
            {
                "actions": [
                    "Microsoft.DBforPostgreSQL/flexibleServers/firewallRules/delete",
                    "Microsoft.DBforPostgreSQL/flexibleServers/firewallRules/read",
                    "Microsoft.DBforPostgreSQL/flexibleServers/firewallRules/write",
                    "Microsoft.DBforPostgreSQL/flexibleServers/databases/write",
                    "Microsoft.DBforPostgreSQL/flexibleServers/databases/read",
                    "Microsoft.DBforPostgreSQL/flexibleServers/databases/delete",
                    "Microsoft.DBforPostgreSQL/flexibleServers/write",
                    "Microsoft.DBforPostgreSQL/flexibleServers/delete",
                    "Microsoft.DBforPostgreSQL/flexibleServers/read",
                    "Microsoft.DBforPostgreSQL/flexibleServers/databases/write",
                    "Microsoft.DBforPostgreSQL/flexibleServers/databases/read",
                    "Microsoft.DBforPostgreSQL/flexibleServers/databases/delete",
                    "Microsoft.ContainerRegistry/registries/*",
                    "Microsoft.ManagedIdentity/userAssignedIdentities/*",
                    "Microsoft.Storage/storageAccounts/*",
                    "Microsoft.App/connectedEnvironments/*",
                    "Microsoft.App/containerApps/*",
                    "Microsoft.App/managedEnvironments/checknameavailability/action",
                    "Microsoft.App/managedEnvironments/join/action",
                    "Microsoft.App/managedEnvironments/read",
                    "Microsoft.Authorization/*",
                    "Microsoft.ClassicCompute/virtualMachines/extensions/*",
                    "Microsoft.ClassicStorage/storageAccounts/listKeys/action",
                    "Microsoft.Compute/virtualMachines/extensions/*",
                    "Microsoft.HybridCompute/machines/extensions/write",
                    "Microsoft.Insights/alertRules/*",
                    "Microsoft.Insights/diagnosticSettings/*",
                    "Microsoft.KeyVault/*",
                    "Microsoft.Management/managementGroups/read",
                    "Microsoft.Network/*",
                    "Microsoft.OperationalInsights/*",
                    "Microsoft.OperationsManagement/*",
                    "Microsoft.ResourceHealth/availabilityStatuses/read",
                    "Microsoft.Resources/deployments/*",
                    "Microsoft.Resources/subscriptions/read",
                    "Microsoft.Resources/subscriptions/resourceGroups/read",
                    "Microsoft.Storage/storageAccounts/listKeys/action",
                    "Microsoft.Support/*"
                ],
                "notActions": [
                    "Microsoft.KeyVault/locations/deletedVaults/purge/action",
                    "Microsoft.KeyVault/hsmPools/*",
                    "Microsoft.KeyVault/managedHsms/*"
                ],
                "dataActions": [
                    "Microsoft.ContainerRegistry/registries/repositories/metadata/read",
                    "Microsoft.ContainerRegistry/registries/repositories/content/read",
                    "Microsoft.ContainerRegistry/registries/repositories/metadata/write",
                    "Microsoft.ContainerRegistry/registries/repositories/content/write",
                    "Microsoft.ContainerRegistry/registries/repositories/metadata/delete",
                    "Microsoft.ContainerRegistry/registries/repositories/content/delete"
                ],
                "notDataActions": []
            }
        ]
    }
}
```
