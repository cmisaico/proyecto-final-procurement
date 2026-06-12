resource "azurerm_postgresql_flexible_server" "psql" {
  name                   = var.server_name
  resource_group_name    = var.resource_group_name
  location               = var.location
  version                = "16"
  administrator_login    = var.admin_username
  administrator_password = var.admin_password

  # Dev: B_Standard_B1ms (1 vCPU burstable, 2 GB RAM) ~$13/mes.
  # Prod: GP_Standard_D4s_v3 (4 vCPU, 16 GB RAM) ~$580/mes.
  sku_name = "B_Standard_B1ms"

  # Mínimo soportado por el tier Burstable: 32 GB.
  storage_mb = 32768

  # 7 días es el mínimo permitido; suficiente para recuperar errores en dev.
  backup_retention_days        = 7
  geo_redundant_backup_enabled = false

  zone = "1"
  tags = var.tags

  # high_availability no está disponible en el tier Burstable.

  maintenance_window {
    day_of_week  = 0
    start_hour   = 2
    start_minute = 0
  }
}

resource "azurerm_postgresql_flexible_server_database" "procurement_db" {
  name      = var.db_name
  server_id = azurerm_postgresql_flexible_server.psql.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

resource "azurerm_postgresql_flexible_server_configuration" "max_connections" {
  name      = "max_connections"
  server_id = azurerm_postgresql_flexible_server.psql.id
  # B1ms soporta hasta ~50 conexiones; 25 es suficiente para pruebas dev.
  value = "25"
}

resource "azurerm_postgresql_flexible_server_configuration" "log_min_duration" {
  name      = "log_min_duration_statement"
  server_id = azurerm_postgresql_flexible_server.psql.id
  value     = "1000"  # Log queries > 1 segundo
}

# Acceso público — solo en dev (enable_private_endpoint = false)
# En prod el tráfico va por Private Endpoint y este recurso no se crea.
resource "azurerm_postgresql_flexible_server_firewall_rule" "allow_azure_services" {
  count     = var.enable_private_endpoint ? 0 : 1
  name      = "allow-azure-services"
  server_id = azurerm_postgresql_flexible_server.psql.id
  # 0.0.0.0/0.0.0.0 es el rango especial de Azure que habilita "Allow access from Azure services"
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# Private Endpoint
resource "azurerm_private_endpoint" "psql" {
  count               = var.enable_private_endpoint ? 1 : 0
  name                = "pe-${var.server_name}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.pe_subnet_id
  tags                = var.tags

  private_service_connection {
    name                           = "psc-${var.server_name}"
    private_connection_resource_id = azurerm_postgresql_flexible_server.psql.id
    subresource_names              = ["postgresqlServer"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name = "dns-group-psql"
    private_dns_zone_ids = [var.psql_private_dns_zone_id]
  }
}
