variable "cluster_name" {
  type        = string
  description = "AKS cluster name"
}

variable "resource_group_name" {
  type        = string
  description = "Resource group for the AKS cluster"
}

variable "location" {
  type        = string
  description = "Azure region"
}

variable "kubernetes_version" {
  type        = string
  description = "Kubernetes version"
  default     = "1.29"
}

variable "aks_subnet_id" {
  type        = string
  description = "Subnet ID for AKS nodes"
}

variable "log_analytics_workspace_id" {
  type        = string
  description = "Log Analytics Workspace ID for AKS monitoring"
  default     = ""
}

# ── System node pool ─────────────────────────────────────────────────────────
variable "system_vm_size" {
  type    = string
  default = "Standard_D4ds_v4"
}

variable "system_min_count" {
  type    = number
  default = 1
}

variable "system_max_count" {
  type    = number
  default = 3
}

# ── User node pool (api-gateway, langgraph, embeddings) ───────────────────────
variable "user_vm_size" {
  type    = string
  default = "Standard_D8ds_v4"
}

variable "user_min_count" {
  type    = number
  default = 1
}

variable "user_max_count" {
  type    = number
  default = 5
}

# ── GPU T4 Spot node pool ─────────────────────────────────────────────────────
variable "gpu_t4_enabled" {
  type    = bool
  default = true
}

variable "gpu_t4_min_count" {
  type        = number
  default     = 0
  description = "0 allows scale-to-zero when no GPU workload is scheduled"
}

variable "gpu_t4_max_count" {
  type    = number
  default = 3
}

# ── GPU A10G node pool ────────────────────────────────────────────────────────
variable "gpu_a10_enabled" {
  type    = bool
  default = false
}

variable "gpu_a10_min_count" {
  type    = number
  default = 0
}

variable "gpu_a10_max_count" {
  type    = number
  default = 2
}

variable "tags" {
  type    = map(string)
  default = {}
}
