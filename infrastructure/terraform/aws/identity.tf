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
