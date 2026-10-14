locals {
  images = toset(["attractions-service", "booking-service", "gate-ride-service", "analytics-worker", "migrate", "frontend"])
}

resource "aws_ecr_repository" "app" {
  for_each             = local.images
  name                 = "${var.name}/${each.key}"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "app" {
  for_each   = aws_ecr_repository.app
  repository = each.value.name
  policy     = jsonencode({ rules = [{ rulePriority = 1, description = "Retain latest three images", selection = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 3 }, action = { type = "expire" } }] })
}

resource "aws_cognito_user_pool" "visitors" {
  name                     = "${var.name}-visitors"
  deletion_protection      = "ACTIVE"
  auto_verified_attributes = ["email"]
  username_attributes      = ["email"]
  mfa_configuration        = "OPTIONAL"
  software_token_mfa_configuration {
    enabled = true
  }

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
  }

  user_pool_add_ons {
    advanced_security_mode = "OFF"
  }
}

resource "aws_cognito_user_pool_client" "web" {
  name                          = "wonderland-web"
  user_pool_id                  = aws_cognito_user_pool.visitors.id
  generate_secret               = false
  explicit_auth_flows           = ["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
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

resource "aws_amplify_app" "web" {
  name                     = "${var.name}-web"
  platform                 = "WEB"
  enable_branch_auto_build = false
  custom_rule {
    source = "/<*>"
    target = "/index.html"
    status = "200"
  }
}

resource "aws_amplify_branch" "demo" {
  app_id            = aws_amplify_app.web.id
  branch_name       = "demo"
  enable_auto_build = false
  stage             = "DEVELOPMENT"
}

output "repositories" {
  value = { for k, v in aws_ecr_repository.app : k => v.repository_url }
}

output "pool_id" {
  value = aws_cognito_user_pool.visitors.id
}

output "client_id" {
  value = aws_cognito_user_pool_client.web.id
}

output "amplify_app_id" {
  value = aws_amplify_app.web.id
}

output "frontend_origin" {
  value = "https://${aws_amplify_branch.demo.branch_name}.${aws_amplify_app.web.default_domain}"
}

variable "tls_server_name" {
  type = string
}
variable "hosted_zone_id" {
  type = string
}
resource "aws_acm_certificate" "api" {
  domain_name       = var.tls_server_name
  validation_method = "DNS"
  lifecycle { create_before_destroy = true }
}
resource "aws_route53_record" "certificate" {
  zone_id = var.hosted_zone_id
  name    = tolist(aws_acm_certificate.api.domain_validation_options)[0].resource_record_name
  type    = tolist(aws_acm_certificate.api.domain_validation_options)[0].resource_record_type
  records = [tolist(aws_acm_certificate.api.domain_validation_options)[0].resource_record_value]
  ttl     = 300
}
resource "aws_acm_certificate_validation" "api" {
  certificate_arn         = aws_acm_certificate.api.arn
  validation_record_fqdns = [aws_route53_record.certificate.fqdn]
}
output "certificate_arn" { value = aws_acm_certificate_validation.api.certificate_arn }
