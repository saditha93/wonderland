mock_provider "aws" {}
run "offline_security_plan" {
  command = plan
  variables {
    account_id            = "111111111111"
    region                = "us-east-1"
    stage                 = "offline-test"
    vpc_id                = "vpc-00000000000000000"
    private_subnets       = ["subnet-00000000000000001", "subnet-00000000000000002"]
    listener_arn          = "arn:aws:elasticloadbalancing:us-east-1:111111111111:listener/app/offline/0000000000000000/0000000000000000"
    alb_security_group_id = "sg-00000000000000000"
    tls_server_name       = "api.example.com"
    frontend_origin       = "https://demo.example.com"
  }
  assert {
    condition     = aws_apigatewayv2_integration.alb.connection_type == "VPC_LINK"
    error_message = "Integration must stay private"
  }
  assert {
    condition     = aws_apigatewayv2_integration.alb.tls_config[0].server_name_to_verify == "api.example.com"
    error_message = "Gateway must verify ALB TLS identity"
  }
  assert {
    condition     = aws_apigatewayv2_api.demo.cors_configuration[0].allow_origins == toset(["https://demo.example.com"])
    error_message = "CORS must use one approved origin"
  }
}
