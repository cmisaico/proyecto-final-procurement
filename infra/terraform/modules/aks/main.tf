# AKS Cluster with multi-GPU node pools and Cluster Autoscaler
# Provider: azurerm ~> 4.0

resource "azurerm_kubernetes_cluster" "aks" {
  name                = var.cluster_name
  resource_group_name = var.resource_group_name
  location            = var.location
  dns_prefix          = var.cluster_name
  kubernetes_version  = var.kubernetes_version

  # Standard tier required for Cluster Autoscaler SLA and production uptime guarantee
  sku_tier = "Standard"

  # ── System node pool ────────────────────────────────────────────────────────
  # Runs kube-system pods only; GPU workloads are excluded via node taint.
  default_node_pool {
    name                        = "system"
    vm_size                     = var.system_vm_size
    auto_scaling_enabled        = true
    min_count                   = var.system_min_count
    max_count                   = var.system_max_count
    vnet_subnet_id              = var.aks_subnet_id
    os_disk_size_gb             = 128
    os_disk_type                = "Managed"
    only_critical_addons_scheduled = true

    node_labels = {
      "nodepool" = "system"
    }

    upgrade_settings {
      max_surge = "33%"
    }
  }

  # ── Cluster Autoscaler profile ───────────────────────────────────────────────
  # GPU pools scale to zero when idle; scale-up triggers when a pod is Pending
  # due to insufficient nvidia.com/gpu resources.
  auto_scaler_profile {
    balance_similar_node_groups      = false  # GPU pools are not balanced (different SKUs)
    expander                         = "least-waste"
    max_graceful_termination_sec     = 600    # 10 min for model teardown
    scale_down_delay_after_add       = "10m"  # Avoid flapping after GPU node provision
    scale_down_unneeded              = "10m"
    scan_interval                    = "10s"
    skip_nodes_with_local_storage    = false
    skip_nodes_with_system_pods      = true
    # GPU nodes can take 5–8 min to provision; allow longer unready time
    max_node_provisioning_time       = "15m"
    new_pod_scale_up_delay           = "0s"
  }

  identity {
    type = "SystemAssigned"
  }

  network_profile {
    network_plugin    = "azure"
    network_policy    = "calico"
    load_balancer_sku = "standard"
    outbound_type     = "loadBalancer"
  }

  # OMS / Container Insights (optional — skip if log_analytics_workspace_id is empty)
  dynamic "oms_agent" {
    for_each = var.log_analytics_workspace_id != "" ? [1] : []
    content {
      log_analytics_workspace_id = var.log_analytics_workspace_id
    }
  }

  tags = var.tags
}

# ── User node pool ─────────────────────────────────────────────────────────────
# Runs: api-gateway, langgraph, embeddings, qdrant, postgres, minio
resource "azurerm_kubernetes_cluster_node_pool" "user" {
  name                  = "user"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.aks.id
  vm_size               = var.user_vm_size
  auto_scaling_enabled  = true
  min_count             = var.user_min_count
  max_count             = var.user_max_count
  vnet_subnet_id        = var.aks_subnet_id
  os_disk_size_gb       = 128
  os_disk_type          = "Managed"

  node_labels = {
    "nodepool" = "user"
  }

  upgrade_settings {
    max_surge = "33%"
  }

  tags = var.tags
}

# ── GPU T4 Spot node pool ──────────────────────────────────────────────────────
# SKU: Standard_NC4as_T4_v3 — 4 vCPU, 28 GB RAM, 1× NVIDIA T4 (16 GB VRAM)
# Spot pricing: ~$0.158/hr (vs $0.526 on-demand) — suitable for dev/academic workloads
# min_count=0 enables scale-to-zero; a Pending vLLM pod triggers scale-up.
resource "azurerm_kubernetes_cluster_node_pool" "gpu_t4" {
  count = var.gpu_t4_enabled ? 1 : 0

  name                  = "gput4"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.aks.id
  vm_size               = "Standard_NC4as_T4_v3"
  auto_scaling_enabled  = true
  min_count             = var.gpu_t4_min_count
  max_count             = var.gpu_t4_max_count
  vnet_subnet_id        = var.aks_subnet_id
  os_disk_size_gb       = 128
  os_disk_type          = "Managed"

  # Spot configuration
  priority        = "Spot"
  eviction_policy = "Delete"
  spot_max_price  = -1  # Pay market price; -1 = no cap

  node_taints = [
    "nvidia.com/gpu=present:NoSchedule",
    "kubernetes.azure.com/scalesetpriority=spot:NoSchedule",
  ]

  node_labels = {
    "nodepool"  = "gpu"
    "hardware"  = "nvidia-t4"
    "gpu-vram"  = "16"
    "gpu-arch"  = "turing"
    "spot"      = "true"
  }

  upgrade_settings {
    max_surge = "1"  # One node at a time to minimize GPU disruption
  }

  tags = var.tags
}

# ── GPU A10G (A10) On-Demand node pool ─────────────────────────────────────────
# SKU: Standard_NV6ads_A10_v5 — 6 vCPU, 55 GB RAM, 1× NVIDIA A10 (24 GB VRAM)
# On-demand pricing: ~$1.354/hr — production inference with FP16 7B or AWQ 14B
resource "azurerm_kubernetes_cluster_node_pool" "gpu_a10" {
  count = var.gpu_a10_enabled ? 1 : 0

  name                  = "gpua10"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.aks.id
  vm_size               = "Standard_NV6ads_A10_v5"
  auto_scaling_enabled  = true
  min_count             = var.gpu_a10_min_count
  max_count             = var.gpu_a10_max_count
  vnet_subnet_id        = var.aks_subnet_id
  os_disk_size_gb       = 256
  os_disk_type          = "Managed"

  node_taints = [
    "nvidia.com/gpu=present:NoSchedule",
  ]

  node_labels = {
    "nodepool"  = "gpu"
    "hardware"  = "nvidia-a10g"
    "gpu-vram"  = "24"
    "gpu-arch"  = "ampere"
    "spot"      = "false"
  }

  upgrade_settings {
    max_surge = "1"
  }

  tags = var.tags
}