output "acr_login_server" {
  value       = module.acr.acr_login_server
  description = "ACR login server URL"
}

output "keyvault_uri" {
  value       = module.keyvault.kv_uri
  description = "Key Vault URI"
}

output "postgres_fqdn" {
  value       = module.postgres.psql_fqdn
  description = "PostgreSQL FQDN"
}

output "storage_blob_endpoint" {
  value       = module.storage.primary_blob_endpoint
  description = "Storage Account blob endpoint"
}

output "grafana_endpoint" {
  value       = module.monitoring.grafana_endpoint
  description = "Managed Grafana endpoint"
}

output "law_workspace_id" {
  value       = module.monitoring.law_workspace_id
  description = "Log Analytics Workspace ID (for AKS integration)"
}
