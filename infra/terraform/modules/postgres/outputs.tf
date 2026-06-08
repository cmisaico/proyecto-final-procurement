output "psql_id"          { value = azurerm_postgresql_flexible_server.psql.id }
output "psql_fqdn"        { value = azurerm_postgresql_flexible_server.psql.fqdn }
output "psql_server_name" { value = azurerm_postgresql_flexible_server.psql.name }
output "db_name"          { value = azurerm_postgresql_flexible_server_database.procurement_db.name }
