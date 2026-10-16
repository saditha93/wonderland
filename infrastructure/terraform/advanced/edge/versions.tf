terraform {
  required_version = "= 1.16.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "= 6.68.0" }
  }
}

provider "aws" {
  region              = var.region
  allowed_account_ids = [var.account_id]
  default_tags {
    tags = { Project = "wonderland", ManagedBy = "terraform", Stage = var.stage }
  }
}

variable "region" {
  type = string
}

variable "account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "Use an explicit 12-digit account ID."
  }
}

variable "stage" {
  type = string
}

variable "name" {
  type    = string
  default = "wonderland-demo"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,24}$", var.name))
    error_message = "Use a short lowercase resource prefix."
  }
}

