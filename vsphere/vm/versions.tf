terraform {
  required_version = ">= 0.13"

  required_providers {
    vsphere = {
      source  = "vmware/vsphere"
      version = ">= 2.0"
    }
    ignition = {
      source  = "community-terraform-providers/ignition"
      version = ">= 2.0"
    }
  }
}
