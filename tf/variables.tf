variable "azure_location" {
  description = "the azure region to deploy resources in."
  type        = string
  default     = "East US"
}

variable "app_name" {
  description = "the base name for the application and related resources."
  type        = string
  default     = "ds-axiaai-carriage-services"
}

variable "image_tag" {
  description = "the docker image tag to deploy."
  type        = string
  default     = "latest"
}

variable "container_port" {
  description = "the port the container application listens on."
  type        = number
  default     = 8000
}

variable "twilio_account_sid" {
  description = "twilio account sid."
  type        = string

}

variable "twilio_auth_token" {
  description = "twilio auth token."
  type        = string

}

variable "twilio_phone_numbers" {
  description = "JSON array of twilio phone numbers for outbound calls, e.g. [\"+1234567890\", \"+0987654321\"]"
  type        = string
}

variable "twilio_tts_voice" {
  description = "the twilio voice to use."
  type        = string
  default     = "alice"
}

variable "voicemail_detection_model" {
  description = "openai model for voicemail detection."
  type        = string
  default     = "gpt-4o-2024-08-06"
}

variable "openai_api_key" {
  description = "openai api key."
  type        = string

}

variable "elevenlabs_api_key" {
  description = "ElevenLabs API key for TTS service."
  type        = string
}

variable "vnet_cidr" {
  description = "cidr block for the virtual network."
  type        = string
  default     = "10.0.0.0/16"
}

variable "db_sku" {
  description = "sku for the postgresql flexible server."
  type        = string
  default     = "B_Standard_B1ms"
}

variable "db_name" {
  description = "name for the postgresql database."
  type        = string
  default     = "carriage"
}

variable "db_user" {
  description = "username for the postgresql database."
  type        = string
  default     = "carriageadmin"
}

variable "subscription_id" {
  description = "azure subscription id for resource deployment."
  type        = string
}

variable "resource_group_name" {
  description = "name of the azure resource group."
  type        = string
}

variable "resource_group_location" {
  description = "location for the azure resource group."
  type        = string
  default     = "East US"
}

variable "client_id" {
  description = "azure service principal id"
  type        = string
}

variable "client_secret" {
  description = "azure service principal secret"
  type        = string
}

variable "tenant_id" {
  description = "azure tenant id"
  type        = string
}

variable "intent_classification_model" {
  description = "openai model for intent classification."
  type        = string
  default     = "gpt-4o-2024-08-06"
}

variable "tts_provider" {
  description = "TTS provider selection (openai or elevenlabs)."
  type        = string
  default     = "elevenlabs"
}

variable "static_recordings_dir" {
  description = "directory for static recordings."
  type        = string
  default     = "data/static_recordings"
}

variable "dynamic_recordings_dir" {
  description = "directory for dynamic recordings."
  type        = string
  default     = "data/dynamic_recordings"
}

variable "enable_profiling" {
  description = "enable profiling ('1' for enabled, '0' for disabled)."
  type        = string
  default     = "0"
}
variable "admin_api_key" {
  description = "admin API key for authentication."
  type        = string
}

variable "user_api_key" {
  description = "user API key for authentication."
  type        = string
}

variable "dynamics_erp_booking" {
  description = "enable Dynamics 365 ERP booking integration."
  type        = bool
  default     = false
}

variable "dynamics_api_url" {
  description = "Dynamics 365 API URL."
  type        = string
  default     = null
}

variable "dynamics_tenant_id" {
  description = "Dynamics 365 Azure tenant ID."
  type        = string
  default     = null
}

variable "dynamics_client_id" {
  description = "Dynamics 365 application client ID."
  type        = string
  default     = null
}

variable "dynamics_client_secret" {
  description = "Dynamics 365 application client secret."
  type        = string
  default     = null
}
