variable "keyvault_name"          { type = string }
variable "resource_group_name"    { type = string }
variable "location"               { type = string }
variable "pe_subnet_id"           { type = string }
variable "kv_private_dns_zone_id" { type = string }
variable "enable_private_endpoint" {
  type    = bool
  default = false
}
variable "tags"                   {
  type = map(string)
  default = {}
}
