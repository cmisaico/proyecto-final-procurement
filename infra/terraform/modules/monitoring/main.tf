resource "azurerm_log_analytics_workspace" "law" {
  name                = var.law_name
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = "PerGB2018"
  # Dev: 30 días — los primeros 31 días son gratuitos en PerGB2018.
  # Retener más días incurre en ~$0.12/GB/día adicional.
  # Prod: 90 días para cumplir con auditoría.
  retention_in_days = 30
  tags              = var.tags
}

resource "azurerm_dashboard_grafana" "grafana" {
  name                              = var.grafana_name
  location                          = var.location
  resource_group_name               = var.resource_group_name
  sku                               = "Standard"
  grafana_major_version             = 12
  zone_redundancy_enabled           = false
  api_key_enabled                   = true
  deterministic_outbound_ip_enabled = true

  identity {
    type = "SystemAssigned"
  }

  tags = var.tags
}

# Asignar rol de Monitoring Reader a Grafana para leer métricas de Azure Monitor
resource "azurerm_role_assignment" "grafana_monitoring_reader" {
  scope                = var.subscription_id
  role_definition_name = "Monitoring Reader"
  principal_id         = azurerm_dashboard_grafana.grafana.identity[0].principal_id
}
