terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.111.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }
   backend "azurerm" {
      resource_group_name  = ""
      storage_account_name = ""
      container_name       = ""
      key                  = ""
  }
}

provider "azurerm" {
  features {}
  # Otherwise the provider requires nigh all permissions to run
  skip_provider_registration = true
  subscription_id = var.subscription_id
}

data "azurerm_client_config" "current" {}

resource "azurerm_log_analytics_workspace" "main" {
  name                = "${var.app_name}-log-analytics"
  location            = var.resource_group_location
  resource_group_name = var.resource_group_name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "random_password" "db_password" {
  length  = 16
  special = false
}

resource "azurerm_postgresql_flexible_server" "main" {
  name                   = "${var.app_name}-db-storage"
  resource_group_name    = var.resource_group_name
  location               = "eastus2"
  version                = "16"
  administrator_login    = var.db_user
  administrator_password = random_password.db_password.result
  sku_name               = var.db_sku
  storage_mb             = 32768
  zone                   = "2"
  public_network_access_enabled = true
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_services" {
  name             = "AllowAllAzureServices"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

resource "azurerm_postgresql_flexible_server_database" "main" {
  name      = var.db_name
  server_id = azurerm_postgresql_flexible_server.main.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

locals {
  all_secrets = {
    # Database secrets
    "POSTGRES_HOST"     = azurerm_postgresql_flexible_server.main.fqdn
    "POSTGRES_PORT"     = "5432"
    "POSTGRES_DB"       = var.db_name
    "POSTGRES_USER"     = var.db_user
    "POSTGRES_PASSWORD" = random_password.db_password.result

    # Application secrets
    "TWILIO_ACCOUNT_SID"                   = var.twilio_account_sid
    "TWILIO_AUTH_TOKEN"                    = var.twilio_auth_token
    "TWILIO_PHONE_NUMBERS"                 = var.twilio_phone_numbers
    "TWILIO_TTS_VOICE"                     = var.twilio_tts_voice
    "VOICEMAIL_DETECTION_MODEL"            = var.voicemail_detection_model
    "OPENAI_API_KEY"                       = var.openai_api_key
    "ELEVENLABS_API_KEY"                   = var.elevenlabs_api_key
    "INTENT_CLASSIFICATION_MODEL"          = var.intent_classification_model
    "TTS_PROVIDER"                         = var.tts_provider
    "STATIC_RECORDINGS_DIR"                = var.static_recordings_dir
    "DYNAMIC_RECORDINGS_DIR"               = var.dynamic_recordings_dir
    "ADMIN_API_KEY"                        = var.admin_api_key
    "USER_API_KEY"                         = var.user_api_key

    # Azure secrets
    "ARM_SUBSCRIPTION_ID"   = var.subscription_id
    "ARM_CLIENT_ID"         = var.client_id
    "ARM_TENANT_ID"         = var.tenant_id
    "ARM_CLIENT_SECRET"     = var.client_secret
    "APP_NAME"              = var.app_name
    "RESOURCE_GROUP_NAME"   = var.resource_group_name

    "DYNAMICS_API_URL"        = var.dynamics_api_url
    "DYNAMICS_TENANT_ID"      = var.dynamics_tenant_id
    "DYNAMICS_CLIENT_ID"      = var.dynamics_client_id
    "DYNAMICS_CLIENT_SECRET"  = var.dynamics_client_secret
  }
}

resource "azurerm_key_vault" "main" {
  name                        = "kv${random_string.short_unique_suffix.result}"
  location                    = var.resource_group_location
  resource_group_name         = var.resource_group_name
  tenant_id                   = data.azurerm_client_config.current.tenant_id
  sku_name                    = "standard"
  soft_delete_retention_days  = 7
  enable_rbac_authorization   = true
  network_acls {
    default_action = "Allow"
    bypass         = "AzureServices"
  }
}

resource "azurerm_role_assignment" "kv_terraform" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_key_vault_secret" "all" {
  for_each     = local.all_secrets
  name         = lower(replace(each.key, "_", "-"))
  value        = each.value
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [
    azurerm_role_assignment.kv_terraform,
    azurerm_postgresql_flexible_server.main
  ]
}

resource "azurerm_container_registry" "main" {
  name                = replace(var.app_name, "-", "")
  resource_group_name = var.resource_group_name
  location            = var.resource_group_location
  sku                 = "Standard"
  admin_enabled       = false
}

resource "azurerm_container_app_environment" "main" {
  name                       = "${var.app_name}-cae"
  location                   = var.resource_group_location
  resource_group_name        = var.resource_group_name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  timeouts {
    create = "5m"
  }
}

resource "azurerm_user_assigned_identity" "workload" {
  name                = "${var.app_name}-identity"
  location            = var.resource_group_location
  resource_group_name = var.resource_group_name
}

resource "azurerm_role_assignment" "acr_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.workload.principal_id
}

resource "azurerm_container_app" "main" {
  name                         = "${var.app_name}-app"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"

  identity {
    type         = "SystemAssigned, UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.workload.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.workload.id
  }


  timeouts {
    create = "5m"
  }
  template {
    min_replicas = 0
    max_replicas = 1

    container {
      name    = var.app_name
      image   = "${azurerm_container_registry.main.login_server}/${var.resource_group_name}:${var.image_tag}"
      cpu     = 2
      memory  = "4Gi"

      env {
        name  = "AZURE_STORAGE_CONNECTION_STRING"
        value = azurerm_storage_account.main.primary_connection_string
      }
      env {
        name  = "AZURE_STORAGE_STATIC_CONTAINER_NAME_OAI"
        value = azurerm_storage_container.static_recordings_oai.name
      }
      env {
        name  = "AZURE_STORAGE_STATIC_CONTAINER_NAME_11LABS"
        value = azurerm_storage_container.static_recordings_11labs.name
      }
      env {
        name  = "AZURE_STORAGE_DYNAMIC_CONTAINER_NAME"
        value = azurerm_storage_container.dynamic_recordings.name
      }
      dynamic "env" {
        for_each = azurerm_key_vault_secret.all
        content {
          name  = upper(replace(env.value.name, "-", "_"))
          value = env.value.value
        }
      }

    }
  }

  ingress {
    external_enabled = true
    target_port      = var.container_port
    transport        = "http"
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  depends_on = [
    azurerm_role_assignment.acr_pull
  ]
}

resource "azurerm_container_app" "admin" {
  name                         = "${var.app_name}-adm"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"

  identity {
    type         = "SystemAssigned, UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.workload.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.workload.id
  }

  timeouts {
    create = "5m"
  }

  template {
    min_replicas = 0
    max_replicas = 1

    container {
      name    = "${var.app_name}-adm"
      image   = "${azurerm_container_registry.main.login_server}/${var.resource_group_name}:${var.image_tag}"
      cpu     = 2
      memory  = "4Gi"
      command = ["uvicorn", "carriage_services.main:admin_app", "--host", "0.0.0.0", "--port", "8001"]

      env {
        name  = "AZURE_STORAGE_CONNECTION_STRING"
        value = azurerm_storage_account.main.primary_connection_string
      }
      env {
        name  = "AZURE_STORAGE_STATIC_CONTAINER_NAME_OAI"
        value = azurerm_storage_container.static_recordings_oai.name
      }
      env {
        name  = "AZURE_STORAGE_STATIC_CONTAINER_NAME_11LABS"
        value = azurerm_storage_container.static_recordings_11labs.name
      }
      env {
        name  = "AZURE_STORAGE_DYNAMIC_CONTAINER_NAME"
        value = azurerm_storage_container.dynamic_recordings.name
      }
      dynamic "env" {
        for_each = azurerm_key_vault_secret.all
        content {
          name  = upper(replace(env.value.name, "-", "_"))
          value = env.value.value
        }
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8001
    transport        = "http"
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  depends_on = [
    azurerm_role_assignment.acr_pull
  ]
}

resource "azurerm_role_assignment" "key_vault_reader_admin" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_container_app.admin.identity[0].principal_id

  depends_on = [
    azurerm_role_assignment.kv_terraform
  ]
}


resource "azurerm_role_assignment" "key_vault_reader" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_container_app.main.identity[0].principal_id

  depends_on = [
    azurerm_role_assignment.kv_terraform
  ]
}
resource "random_string" "unique_suffix" {
  length  = 8
  special = false
  upper   = false
}
resource "random_string" "short_unique_suffix" {
  length  = 4
  special = false
  upper   = false
}
resource "azurerm_storage_account" "main" {
  name                     = "${substr(replace(var.app_name, "-", ""), 0, 16)}${random_string.unique_suffix.result}"
  resource_group_name      = var.resource_group_name
  location                 = var.resource_group_location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_role_assignment" "storage_blob_contributor" {
  scope                = azurerm_storage_account.main.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_storage_container" "static_recordings_oai" {
  name                  = "static-recordings-oai"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "blob"

  depends_on = [
    azurerm_role_assignment.storage_blob_contributor
  ]
}

resource "azurerm_storage_container" "static_recordings_11labs" {
  name                  = "static-recordings-11labs"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "blob"

  depends_on = [
    azurerm_role_assignment.storage_blob_contributor
  ]
}

resource "azurerm_storage_container" "dynamic_recordings" {
  name                  = "dynamic-recordings"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "blob"

  depends_on = [
    azurerm_role_assignment.storage_blob_contributor
  ]
}
