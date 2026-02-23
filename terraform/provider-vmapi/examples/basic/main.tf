terraform {
  required_version = ">= 1.6.0"

  required_providers {
    vmapi = {
      source  = "phyllisnelson/vmapi"
      version = "0.1.0"
    }
  }
}

provider "vmapi" {
  base_url = var.base_url
  api_key  = var.api_key
}

variable "base_url" {
  type    = string
  default = "http://localhost:8000"
}

variable "api_key" {
  type      = string
  sensitive = true
  default   = "changeme"
}

data "vmapi_flavors" "all" {
  limit  = 50
  offset = 0
}

data "vmapi_images" "all" {
  limit  = 50
  offset = 0
}

locals {
  flavor_id = data.vmapi_flavors.all.flavors[0].id
  image_id  = data.vmapi_images.all.images[0].id
}

resource "vmapi_vm" "example" {
  name      = "tf-vm-example"
  flavor_id = local.flavor_id
  image_id  = local.image_id

  metadata = {
    managed_by = "terraform"
  }
}

resource "vmapi_volume" "example" {
  name    = "tf-volume-example"
  size_gb = 20

  metadata = {
    managed_by = "terraform"
  }
}

output "vm_id" {
  value = vmapi_vm.example.id
}

output "volume_id" {
  value = vmapi_volume.example.id
}
