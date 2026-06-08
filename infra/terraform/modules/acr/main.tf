resource "azurerm_container_registry" "acr" {
  name                = var.acr_name
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = var.sku
  admin_enabled       = var.admin_enabled
  tags                = var.tags

  # network_rule_set y georeplications solo disponibles en SKU Premium.
  dynamic "network_rule_set" {
    for_each = var.sku == "Premium" ? [1] : []
    content {
      default_action = "Deny"
      ip_rule        = []
    }
  }

  dynamic "georeplications" {
    for_each = var.sku == "Premium" ? [1] : []
    content {
      location                = "brazilsouth"
      zone_redundancy_enabled = false
      tags                    = var.tags
    }
  }
}

# Private Endpoint solo se crea cuando el SKU es Premium y está habilitado.
resource "azurerm_private_endpoint" "acr" {
  count               = var.enable_private_endpoint ? 1 : 0
  name                = "pe-${var.acr_name}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.pe_subnet_id
  tags                = var.tags

  private_service_connection {
    name                           = "psc-${var.acr_name}"
    private_connection_resource_id = azurerm_container_registry.acr.id
    subresource_names              = ["registry"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "dns-group-acr"
    private_dns_zone_ids = [var.acr_private_dns_zone_id]
  }
}
