# ── AKS Cluster con node pools GPU y Cluster Autoscaler ─────────────────────
module "aks" {
  source = "./modules/aks"

  cluster_name               = var.aks_cluster_name
  resource_group_name        = var.resource_group_name
  location                   = var.location
  kubernetes_version         = var.kubernetes_version
  aks_subnet_id              = var.aks_subnet_id
  log_analytics_workspace_id = ""   # Rellenar si se usa Container Insights

  # Node pool sizing
  system_min_count = 1
  system_max_count = 3
  user_min_count   = 1
  user_max_count   = 5

  # GPU T4 Spot — dev/académico, escala a 0 cuando no hay carga
  gpu_t4_enabled   = true
  gpu_t4_min_count = 0
  gpu_t4_max_count = 3

  # GPU A10G — producción, deshabilitado por defecto; activar en prod
  gpu_a10_enabled   = false
  gpu_a10_min_count = 0
  gpu_a10_max_count = 2

  tags = var.tags
}

# Rol ACR Pull para que los nodos AKS puedan descargar imágenes desde ACR
resource "azurerm_role_assignment" "aks_acr_pull" {
  scope                = module.acr.id
  role_definition_name = "AcrPull"
  principal_id         = module.aks.kubelet_identity_object_id
}

# Las DNS zones solo se buscan cuando enable_private_endpoints = true.
# En dev (false) los data sources no se ejecutan y no fallan si las zonas no existen.
data "azurerm_private_dns_zone" "acr" {
  count               = var.enable_private_endpoints ? 1 : 0
  name                = "privatelink.azurecr.io"
  resource_group_name = var.resource_group_name
}

data "azurerm_private_dns_zone" "kv" {
  count               = var.enable_private_endpoints ? 1 : 0
  name                = "privatelink.vaultcore.azure.net"
  resource_group_name = var.resource_group_name
}

data "azurerm_private_dns_zone" "psql" {
  count               = var.enable_private_endpoints ? 1 : 0
  name                = "privatelink.postgres.database.azure.com"
  resource_group_name = var.resource_group_name
}

data "azurerm_private_dns_zone" "storage" {
  count               = var.enable_private_endpoints ? 1 : 0
  name                = "privatelink.blob.core.windows.net"
  resource_group_name = var.resource_group_name
}

# Módulo ACR
module "acr" {
  source = "./modules/acr"

  acr_name                = var.acr_name
  resource_group_name     = var.resource_group_name
  location                = var.location
  pe_subnet_id            = var.pe_subnet_id
  acr_private_dns_zone_id = var.enable_private_endpoints ? data.azurerm_private_dns_zone.acr[0].id : ""
  tags                    = var.tags

  # Dev: Basic sin private endpoint. Prod: Premium con enable_private_endpoint = true.
  sku                     = var.enable_private_endpoints ? "Premium" : "Basic"
  enable_private_endpoint = var.enable_private_endpoints
  admin_enabled           = !var.enable_private_endpoints
}

# Módulo Key Vault
module "keyvault" {
  source = "./modules/keyvault"

  keyvault_name          = var.keyvault_name
  resource_group_name    = var.resource_group_name
  location               = var.location
  pe_subnet_id             = var.pe_subnet_id
  kv_private_dns_zone_id   = var.enable_private_endpoints ? data.azurerm_private_dns_zone.kv[0].id : ""
  enable_private_endpoint  = var.enable_private_endpoints
  tags                     = var.tags
}

# Módulo PostgreSQL
module "postgres" {
  source = "./modules/postgres"

  server_name              = var.postgres_server_name
  resource_group_name      = var.resource_group_name
  location                 = var.location
  admin_username           = var.postgres_admin_username
  admin_password           = var.postgres_admin_password
  db_name                  = var.postgres_db_name
  pe_subnet_id             = var.pe_subnet_id
  psql_private_dns_zone_id = var.enable_private_endpoints ? data.azurerm_private_dns_zone.psql[0].id : ""
  enable_private_endpoint  = var.enable_private_endpoints
  tags                     = var.tags
}

# Módulo Storage
module "storage" {
  source = "./modules/storage"

  storage_account_name        = var.storage_account_name
  resource_group_name         = var.resource_group_name
  location                    = var.location
  pe_subnet_id                = var.pe_subnet_id
  storage_private_dns_zone_id = var.enable_private_endpoints ? data.azurerm_private_dns_zone.storage[0].id : ""
  enable_private_endpoint     = var.enable_private_endpoints
  tags                        = var.tags
}

# Módulo Monitoring
module "monitoring" {
  source = "./modules/monitoring"

  law_name            = var.law_name
  grafana_name        = var.grafana_name
  resource_group_name = var.resource_group_monitoring_name
  location            = var.location
  subscription_id     = "/subscriptions/${var.subscription_id}"
  tags                = var.tags
}
