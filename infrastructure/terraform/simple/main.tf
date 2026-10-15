terraform {
  backend "local" { path = "../../../secrets/simple-cloud/terraform.tfstate" }
  required_version = "= 1.16.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "= 6.68.0" }
  }
}
provider "aws" {
  region              = "us-east-1"
  allowed_account_ids = [var.account_id]
  default_tags { tags = { Project = "wonderland", Stack = "wonderland-demo", ManagedBy = "terraform" } }
}
# Stage creation checks the parent API tags. Avoid a second implicit TagResource
# authorization call; ownership remains on the already tagged API itself.
provider "aws" {
  alias               = "api_stage"
  region              = "us-east-1"
  allowed_account_ids = [var.account_id]
}
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
locals {
  name   = "wonderland-demo"
  bucket = "${local.name}-${var.account_id}-artifacts"
  images = toset(["attractions-service", "booking-service", "gate-ride-service", "analytics-worker", "migrate", "frontend"])
}
resource "aws_vpc" "demo" {
  cidr_block           = "10.70.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
}
resource "aws_subnet" "demo" {
  vpc_id            = aws_vpc.demo.id
  cidr_block        = "10.70.1.0/24"
  availability_zone = var.availability_zone
}
resource "aws_internet_gateway" "demo" { vpc_id = aws_vpc.demo.id }
resource "aws_route_table" "demo" {
  vpc_id = aws_vpc.demo.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.demo.id
  }
}
resource "aws_route_table_association" "demo" {
  subnet_id      = aws_subnet.demo.id
  route_table_id = aws_route_table.demo.id
}
resource "aws_security_group" "demo" {
  name        = local.name
  description = "HTTPS demo API and ACME challenge; administration uses SSM"
  vpc_id      = aws_vpc.demo.id
  ingress {
    description = "Public ACME HTTP-01 challenge only"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "TLS API; origin token and application authorization required"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_network_interface" "demo" {
  subnet_id       = aws_subnet.demo.id
  security_groups = [aws_security_group.demo.id]
}
resource "aws_iam_role" "demo" {
  name                 = "${local.name}-ec2"
  permissions_boundary = "arn:aws:iam::${var.account_id}:policy/WonderlandRuntimeBoundary"
  assume_role_policy   = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_role_policy" "runtime" {
  name   = "wonderland-runtime"
  role   = aws_iam_role.demo.id
  policy = var.runtime_policy
}
resource "aws_iam_instance_profile" "demo" {
  name = "${local.name}-ec2"
  role = aws_iam_role.demo.name
}
resource "aws_instance" "demo" {
  ami                         = var.ami_id
  instance_type               = var.instance_type
  iam_instance_profile        = aws_iam_instance_profile.demo.name
  user_data                   = var.bootstrap_script
  user_data_replace_on_change = true
  volume_tags                 = { Project = "wonderland", Stack = local.name, ManagedBy = "terraform" }
  primary_network_interface {
    network_interface_id = aws_network_interface.demo.id
  }
  root_block_device {
    encrypted             = true
    volume_size           = 30
    volume_type           = "gp3"
    delete_on_termination = true
  }
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
    instance_metadata_tags      = "disabled"
  }
  depends_on = [aws_iam_role_policy.runtime, aws_route_table_association.demo]
  lifecycle { prevent_destroy = true }
}
resource "aws_eip" "demo" { domain = "vpc" }
resource "aws_eip_association" "demo" {
  allocation_id        = aws_eip.demo.id
  network_interface_id = aws_network_interface.demo.id
  depends_on           = [aws_instance.demo]
}
resource "aws_s3_bucket" "artifacts" {
  bucket        = local.bucket
  force_destroy = false
  lifecycle { prevent_destroy = true }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_policy" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Deny", Principal = "*", Action = "s3:*", Resource = [aws_s3_bucket.artifacts.arn, "${aws_s3_bucket.artifacts.arn}/*"], Condition = { Bool = { "aws:SecureTransport" = "false" } } }] })
}
resource "aws_ecr_repository" "app" {
  for_each             = local.images
  name                 = "${local.name}/${each.key}"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  encryption_configuration { encryption_type = "AES256" }
  image_scanning_configuration { scan_on_push = true }
}
resource "aws_ecr_lifecycle_policy" "app" {
  for_each   = aws_ecr_repository.app
  repository = each.value.name
  policy     = jsonencode({ rules = [{ rulePriority = 1, description = "Keep latest three releases", selection = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 3 }, action = { type = "expire" } }] })
}
resource "aws_cognito_user_pool" "visitors" {
  name                     = "${local.name}-visitors"
  deletion_protection      = "ACTIVE"
  auto_verified_attributes = ["email"]
  username_attributes      = ["email"]
  mfa_configuration        = "OPTIONAL"
  software_token_mfa_configuration { enabled = true }
  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
  }
}
resource "aws_cognito_user_pool_client" "web" {
  name                          = "wonderland-web"
  user_pool_id                  = aws_cognito_user_pool.visitors.id
  generate_secret               = false
  explicit_auth_flows           = ["ALLOW_USER_SRP_AUTH", "ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  prevent_user_existence_errors = "ENABLED"
  access_token_validity         = 15
  id_token_validity             = 15
  refresh_token_validity        = 1
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
  enable_token_revocation = true
}
resource "aws_cognito_user_group" "admins" {
  name         = "administrators"
  user_pool_id = aws_cognito_user_pool.visitors.id
}
resource "aws_amplify_app" "portal" {
  for_each                 = toset(["visitor", "admin"])
  name                     = "${local.name}-${each.key}"
  platform                 = "WEB"
  enable_branch_auto_build = false
  custom_rule {
    source = "/<*>"
    target = "/index.html"
    status = "200"
  }
}
resource "aws_amplify_branch" "portal" {
  for_each          = aws_amplify_app.portal
  app_id            = each.value.id
  branch_name       = "demo"
  enable_auto_build = false
  stage             = "DEVELOPMENT"
}
resource "aws_sqs_queue" "dead" {
  name                      = "${local.name}-dead"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}
resource "aws_sqs_queue" "events" {
  name                       = "${local.name}-events"
  visibility_timeout_seconds = 30
  sqs_managed_sse_enabled    = true
  redrive_policy             = jsonencode({ deadLetterTargetArn = aws_sqs_queue.dead.arn, maxReceiveCount = 5 })
}
resource "aws_secretsmanager_secret" "runtime" {
  name                    = "${local.name}/runtime"
  recovery_window_in_days = 7
}
resource "aws_cloudwatch_log_group" "app" {
  name              = "/wonderland/${local.name}/application"
  retention_in_days = 7
}
resource "aws_apigatewayv2_api" "demo" {
  name          = local.name
  protocol_type = "HTTP"
  cors_configuration {
    allow_origins = [for k, app in aws_amplify_app.portal : "https://demo.${app.default_domain}"]
    allow_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    allow_headers = ["authorization", "content-type", "idempotency-key", "x-request-id", "stripe-signature"]
    max_age       = 300
  }
}
resource "aws_apigatewayv2_integration" "demo" {
  api_id                 = aws_apigatewayv2_api.demo.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "ANY"
  integration_uri        = "https://${aws_eip.demo.public_ip}/api/{proxy}"
  payload_format_version = "1.0"
  timeout_milliseconds   = 29000
  request_parameters     = { "overwrite:header.x-wonderland-gateway" = var.origin_token }
}
resource "aws_apigatewayv2_route" "demo" {
  api_id    = aws_apigatewayv2_api.demo.id
  route_key = "ANY /api/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.demo.id}"
}
resource "aws_apigatewayv2_stage" "demo" {
  provider    = aws.api_stage
  api_id      = aws_apigatewayv2_api.demo.id
  name        = "$default"
  auto_deploy = true
  default_route_settings {
    throttling_burst_limit = 40
    throttling_rate_limit  = 20
  }
}
output "deployment" {
  value = {
    instance_id        = aws_instance.demo.id
    server_ip          = aws_eip.demo.public_ip
    artifact_bucket    = aws_s3_bucket.artifacts.id
    runtime_secret_arn = aws_secretsmanager_secret.runtime.arn
    pool_id            = aws_cognito_user_pool.visitors.id
    client_id          = aws_cognito_user_pool_client.web.id
    api_url            = aws_apigatewayv2_api.demo.api_endpoint
    queue_url          = aws_sqs_queue.events.url
    dead_queue_url     = aws_sqs_queue.dead.url
    repositories       = { for k, v in aws_ecr_repository.app : k => v.repository_url }
    portals            = { for k, v in aws_amplify_app.portal : k => { app_id = v.id, origin = "https://demo.${v.default_domain}" } }
  }
}
