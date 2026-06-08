data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "kv" {
  name                = var.keyvault_name
  location            = var.location
  resource_group_name = var.resource_group_name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"

  # Dev: 7 días (mínimo) permite destruir y recrear el vault sin esperar.
  # Prod: 90 días protege contra borrado accidental.
  soft_delete_retention_days = 7

  # Dev: false — permite terraform destroy sin bloqueo de purge protection.
  # Prod: true — impide borrado permanente accidental de secretos.
  purge_protection_enabled = false

  tags = var.tags

  network_acls {
    bypass         = "AzureServices"
    default_action = "Allow"
  }
}

# Access policy para el usuario/SP de Terraform (para poder crear secrets)
resource "azurerm_key_vault_access_policy" "terraform_sp" {
  key_vault_id = azurerm_key_vault.kv.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = data.azurerm_client_config.current.object_id

  key_permissions     = ["Get", "List", "Create", "Delete", "Update"]
  secret_permissions  = ["Get", "List", "Set", "Delete", "Recover"]
  certificate_permissions = ["Get", "List", "Create"]
}

# Private Endpoint para Key Vault
resource "azurerm_private_endpoint" "kv" {
  count               = var.enable_private_endpoint ? 1 : 0
  name                = "pe-${var.keyvault_name}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.pe_subnet_id
  tags                = var.tags

  private_service_connection {
    name                           = "psc-${var.keyvault_name}"
    private_connection_resource_id = azurerm_key_vault.kv.id
    subresource_names              = ["vault"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name = "dns-group-kv"
    private_dns_zone_ids = [var.kv_private_dns_zone_id]
  }
}
