variable "law_name"           { type = string }
variable "grafana_name"       { type = string }
variable "resource_group_name" { type = string }
variable "location"           { type = string }
variable "subscription_id"    { type = string }
variable "tags"               {
  type = map(string)
  default = {}
}
