variable "hostnames_ip_addresses" {
  type = map(string)
}

variable "ignition" {
  type      = string
  sensitive = true
  default   = ""
}

variable "disk_thin_provisioned" {
  type = bool
}

variable "disk_size" {
  type = number
}

variable "template_uuid" {
  type = string
}

variable "guest_id" {
  type = string
}

variable "resource_pool_id" {
  type = string
}

variable "folder_id" {
  type = string
}

variable "datastore_cluster_id" {
  type = string
}

variable "network_id" {
  type = string
}

variable "datacenter_id" {
  type = string
}

variable "cluster_domain" {
  type = string
}

variable "base_domain" {
  type = string
}

variable "machine_cidr" {
  type = string
}

variable "gateway" {
  type        = string
  description = "Gateway IP for the cluster network."
}

variable "memory" {
  type = number
}

variable "num_cpus" {
  type = number
}

variable "dns_addresses" {
  type = list(string)
}
