output "law_id"              { value = azurerm_log_analytics_workspace.law.id }
output "law_workspace_id"    { value = azurerm_log_analytics_workspace.law.workspace_id }
output "grafana_id"          { value = azurerm_dashboard_grafana.grafana.id }
output "grafana_endpoint"    { value = azurerm_dashboard_grafana.grafana.endpoint }
