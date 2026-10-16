variable "account_id" { type = string }

variable "ami_id" { type = string }

variable "availability_zone" { type = string }

variable "instance_type" {
  type    = string
  default = "m7i-flex.large"
  validation {
    condition     = var.instance_type == "m7i-flex.large"
    error_message = "Only the reviewed Free-plan-eligible demo size is allowed."
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
