variable "acr_name"                { type = string }
variable "resource_group_name"     { type = string }
variable "location"                { type = string }
variable "pe_subnet_id"            { type = string }
variable "acr_private_dns_zone_id" { type = string }
variable "tags"                    {
  type = map(string)
  default = {}
}

# Dev: "Basic" (~$5/mes). Prod: "Premium" (private endpoint + geo-replication).
variable "sku"                     {
  type = string
  default = "Basic"
}
# Solo disponible con SKU Premium.
variable "enable_private_endpoint" {
  type = bool
  default = false
}
# Admin enabled simplifica el push de imágenes en dev sin Service Principal.
variable "admin_enabled"           {
  type = bool
  default = true
}
