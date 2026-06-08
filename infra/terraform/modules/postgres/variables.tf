variable "server_name"             { type = string }
variable "resource_group_name"     { type = string }
variable "location"                { type = string }
variable "admin_username"          { type = string }
variable "admin_password"          {
  type = string
  sensitive = true
}
variable "db_name"                 { type = string }
variable "pe_subnet_id"            { type = string }
variable "psql_private_dns_zone_id" { type = string }
variable "enable_private_endpoint" {
  type    = bool
  default = false
}
variable "tags"                    {
  type = map(string)
  default = {}
}
