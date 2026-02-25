output "acr_login_server" {
  description = "The login server of the Azure Container Registry. Use this to tag and push your Docker image."
  value       = azurerm_container_registry.main.login_server
}


output "key_vault_uri" {
  description = "The URI of the Key Vault for managing secrets."
  value       = azurerm_key_vault.main.vault_uri
}

output "postgresql_fqdn" {
  description = "The FQDN of the PostgreSQL Flexible Server."
  value       = azurerm_postgresql_flexible_server.main.fqdn
}

output "container_app_url" {
  description = "The public FQDN of the Container App service."
  value       = "https://${azurerm_container_app.main.latest_revision_fqdn}"
}

output "storage_account_primary_blob_endpoint" {
  description = "The primary blob endpoint for the storage account."
  value       = azurerm_storage_account.main.primary_blob_endpoint
}
output "admin_app_url" {
  description = "The public FQDN of the Admin Container App service."
  value       = "https://${azurerm_container_app.admin.latest_revision_fqdn}"
}
