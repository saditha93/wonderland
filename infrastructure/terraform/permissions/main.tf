terraform {
  backend "local" {}
  required_version = "= 1.16.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "= 6.68.0" }
  }
}
provider "aws" {
  region              = "us-east-1"
  allowed_account_ids = [var.account_id]
}
variable "account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "Specify the reviewed AWS account."
  }
}
variable "documents" {
  type = map(string)
  validation {
    condition     = toset(keys(var.documents)) == toset(["WonderlandDemoCompute", "WonderlandDemoServices", "WonderlandDemoAccess", "WonderlandDemoDependencies", "WonderlandRuntimeBoundary"])
    error_message = "Only the five Wonderland policy definitions are managed."
  }
}
variable "existing_policies" { type = set(string) }
variable "existing_attachments" { type = set(string) }
variable "descriptions" { type = map(string) }
locals {
  grants = { for name, document in var.documents : name => document if name != "WonderlandRuntimeBoundary" }
}
resource "aws_iam_policy" "definition" {
  for_each    = var.documents
  name        = each.key
  policy      = each.value
  description = var.descriptions[each.key]
  tags        = { Project = "wonderland", Stack = "wonderland-demo" }
  lifecycle { prevent_destroy = true }
}
resource "aws_iam_user_policy_attachment" "deployment" {
  for_each   = local.grants
  user       = "wonderland"
  policy_arn = aws_iam_policy.definition[each.key].arn
}
import {
  for_each = var.existing_policies
  to       = aws_iam_policy.definition[each.key]
  id       = "arn:aws:iam::${var.account_id}:policy/${each.key}"
}
import {
  for_each = var.existing_attachments
  to       = aws_iam_user_policy_attachment.deployment[each.key]
  id       = "wonderland/arn:aws:iam::${var.account_id}:policy/${each.key}"
}
output "retained_permissions" {
  value = "Administrator bootstrap only. Definitions are protected from destruction; application up/down uses the non-root wonderland identity."
}
