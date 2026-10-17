variable "account_id" { type = string }

variable "ami_id" { type = string }

variable "availability_zone" { type = string }

variable "instance_type" {
  type    = string
  default = "m7i-flex.large"
  validation {
    condition     = var.instance_type == "m7i-flex.large"
    error_message = "Use the reviewed Free-plan-eligible 8 GiB full-stack size."
  }
}

variable "bootstrap_script" { type = string }

variable "runtime_policy" { type = string }

variable "origin_token" {
  type      = string
  sensitive = true
  validation {
    condition     = length(var.origin_token) >= 48
    error_message = "Use a generated origin token."
  }
}

variable "server_name" {
  type    = string
  default = "Wonderland Demo Server"
  validation {
    condition     = length(trimspace(var.server_name)) > 0 && length(var.server_name) <= 128
    error_message = "Provide a readable server name of 1–128 characters."
  }
}

variable "ssh_key_name" {
  type    = string
  default = "sliit_test"
}

variable "ssh_allowed_cidr" {
  type = string
  validation {
    condition     = can(cidrhost(var.ssh_allowed_cidr, 0)) && can(regex("^[0-9.]+/32$", var.ssh_allowed_cidr)) && var.ssh_allowed_cidr != "0.0.0.0/32"
    error_message = "SSH requires your single public IPv4 address with /32; broad networks are refused."
  }
}
