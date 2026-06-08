resource "azurerm_storage_account" "st" {
  name                     = var.storage_account_name
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"
  access_tier              = "Hot"
  min_tls_version          = "TLS1_2"
  allow_nested_items_to_be_public = false
  tags                     = var.tags

  blob_properties {
    # Dev: versioning y change_feed deshabilitados — generan transacciones de
    # metadatos continuas que incrementan el costo aunque el volumen sea bajo.
    versioning_enabled  = false
    change_feed_enabled = false

    delete_retention_policy {
      days = 7
    }

    container_delete_retention_policy {
      days = 7
    }
  }

  # Dev: Allow — el private endpoint ya restringe el acceso a nivel de red.
  # Prod: cambiar a Deny con ip_rules específicos.
  network_rules {
    default_action = "Allow"
    bypass         = ["AzureServices"]
  }
}

# Containers (equivalentes a buckets de MinIO)
resource "azurerm_storage_container" "licitaciones" {
  name                  = "licitaciones"
  storage_account_name  = azurerm_storage_account.st.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "processed" {
  name                  = "processed"
  storage_account_name  = azurerm_storage_account.st.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "models" {
  name                  = "models"
  storage_account_name  = azurerm_storage_account.st.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "backups" {
  name                  = "backups"
  storage_account_name  = azurerm_storage_account.st.name
  container_access_type = "private"
}

# Lifecycle policy: borrar datos de prueba después de 30 días.
resource "azurerm_storage_management_policy" "lifecycle" {
  storage_account_id = azurerm_storage_account.st.id

  rule {
    name    = "cleanup-dev-data"
    enabled = true
    filters {
      blob_types = ["blockBlob"]
    }
    actions {
      base_blob {
        # Dev: borrar todo después de 30 días para evitar acumulación de datos de prueba.
        delete_after_days_since_modification_greater_than = 30
      }
    }
  }
}

# Private Endpoint
resource "azurerm_private_endpoint" "storage" {
  count               = var.enable_private_endpoint ? 1 : 0
  name                = "pe-${var.storage_account_name}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.pe_subnet_id
  tags                = var.tags

  private_service_connection {
    name                           = "psc-${var.storage_account_name}"
    private_connection_resource_id = azurerm_storage_account.st.id
    subresource_names              = ["blob"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name = "dns-group-storage"
    private_dns_zone_ids = [var.storage_private_dns_zone_id]
  }
}
