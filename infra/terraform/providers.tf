terraform {
  required_version = ">= 1.7.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 2.50"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  backend "azurerm" {
    resource_group_name  = "rg-procurement-tfstate"
    storage_account_name = "stprocurementtfstate"
    container_name       = "tfstate"
    key                  = "procurement.prod.tfstate"
    subscription_id = "29fd6d9d-066c-43ca-86c4-f4cb1ba371fe"
    tenant_id       = "1a23be34-0a83-4777-8c0d-5b2b24640a65"
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
  subscription_id = "29fd6d9d-066c-43ca-86c4-f4cb1ba371fe"
  tenant_id       = "1a23be34-0a83-4777-8c0d-5b2b24640a65"
}

provider "azuread" {}
provider "random" {}