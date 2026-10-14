variable "vpc_id" {
  type = string
}

variable "private_subnets" {
  type = list(string)
}

variable "listener_arn" {
  type = string
}

variable "alb_security_group_id" {
  type = string
}

variable "tls_server_name" {
  type = string
}

variable "frontend_origin" {
  type = string
}

resource "aws_security_group" "link" {
  name   = "${var.name}-vpc-link"
  vpc_id = var.vpc_id
}

resource "aws_vpc_security_group_egress_rule" "link" {
  security_group_id            = aws_security_group.link.id
  referenced_security_group_id = var.alb_security_group_id
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "alb" {
  security_group_id            = var.alb_security_group_id
  referenced_security_group_id = aws_security_group.link.id
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
}

resource "aws_apigatewayv2_vpc_link" "demo" {
  name               = var.name
  subnet_ids         = var.private_subnets
  security_group_ids = [aws_security_group.link.id]
}

resource "aws_apigatewayv2_api" "demo" {
  name          = var.name
  protocol_type = "HTTP"
  cors_configuration {
    allow_origins  = [var.frontend_origin]
    allow_methods  = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    allow_headers  = ["authorization", "content-type", "idempotency-key", "x-request-id", "stripe-signature"]
    expose_headers = ["x-request-id"]
    max_age        = 300
  }
}

resource "aws_apigatewayv2_integration" "alb" {
  api_id                 = aws_apigatewayv2_api.demo.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "ANY"
  integration_uri        = var.listener_arn
  connection_type        = "VPC_LINK"
  connection_id          = aws_apigatewayv2_vpc_link.demo.id
  payload_format_version = "1.0"
  request_parameters     = { "overwrite:path" = "$request.path" }
  tls_config {
    server_name_to_verify = var.tls_server_name
  }

  timeout_milliseconds = 29000
}

resource "aws_apigatewayv2_route" "proxy" {
  api_id    = aws_apigatewayv2_api.demo.id
  route_key = "ANY /api/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.alb.id}"
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/wonderland/${var.name}/api"
  retention_in_days = 7
}

resource "aws_apigatewayv2_stage" "demo" {
  api_id      = aws_apigatewayv2_api.demo.id
  name        = "$default"
  auto_deploy = true
  default_route_settings {
    throttling_burst_limit = 100
    throttling_rate_limit  = 50
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api.arn
    format          = jsonencode({ requestId = "$context.requestId", status = "$context.status", routeKey = "$context.routeKey", integrationError = "$context.integrationErrorMessage" })
  }
}

output "api_url" {
  value = aws_apigatewayv2_api.demo.api_endpoint
}

