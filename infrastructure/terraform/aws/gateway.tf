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
