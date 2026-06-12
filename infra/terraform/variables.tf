variable "subscription_id" {
  type        = string
  description = "Azure Subscription ID"
}

variable "tenant_id" {
  type        = string
  description = "Azure Tenant ID"
}

variable "location" {
  type        = string
  description = "Azure region"
  default     = "brazilsouth"
}

variable "project" {
  type        = string
  description = "Project name (used in resource names)"
  default     = "procurement"
}

variable "environment" {
  type        = string
  description = "Environment (prod, staging, dev)"
  default     = "dev"
}

variable "enable_private_endpoints" {
  type        = bool
  description = "Crear Private Endpoints y usar acceso privado. Requiere ACR Premium. En dev usar false."
  default     = false
}

variable "resource_group_name" {
  type        = string
  description = "Main resource group name"
}

variable "resource_group_monitoring_name" {
  type        = string
  description = "Monitoring resource group name"
}

variable "vnet_name" {
  type        = string
  description = "Virtual Network name"
}

variable "pe_subnet_id" {
  type        = string
  description = "Private Endpoints subnet ID"
}

variable "acr_name" {
  type        = string
  description = "Azure Container Registry name (globally unique, no dashes)"
}

variable "keyvault_name" {
  type        = string
  description = "Key Vault name"
}

variable "postgres_server_name" {
  type        = string
  description = "PostgreSQL Flexible Server name"
}

variable "postgres_admin_username" {
  type        = string
  description = "PostgreSQL admin username"
  default     = "procureadmin"
}

variable "postgres_admin_password" {
  type        = string
  description = "PostgreSQL admin password"
  sensitive   = true
}

variable "postgres_db_name" {
  type        = string
  description = "Initial database name"
  default     = "procurement_db"
}

variable "storage_account_name" {
  type        = string
  description = "Storage Account name (globally unique, no dashes)"
}

variable "law_name" {
  type        = string
  description = "Log Analytics Workspace name"
}

variable "grafana_name" {
  type        = string
  description = "Azure Managed Grafana name"
}

variable "tags" {
  type        = map(string)
  description = "Common tags for all resources"
  default     = {}
}
