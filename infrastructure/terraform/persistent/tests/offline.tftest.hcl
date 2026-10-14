mock_provider "aws" {
  mock_resource "aws_acm_certificate" {
    defaults = { domain_validation_options = [{ domain_name = "api.example.com", resource_record_name = "_validation.api.example.com", resource_record_type = "CNAME", resource_record_value = "_validation.acm-validations.aws" }] }
  }
}
run "offline_security_plan" {
  command = plan
  variables {
    account_id      = "111111111111"
    region          = "us-east-1"
    stage           = "offline-test"
    tls_server_name = "api.example.com"
    hosted_zone_id  = "Z000000000000000"
  }
  assert {
    condition     = aws_cognito_user_pool_client.web.generate_secret == false
    error_message = "Browser clients cannot hold a secret"
  }
  assert {
    condition     = aws_cognito_user_pool.visitors.deletion_protection == "ACTIVE"
    error_message = "Persistent user pool must be protected"
  }
  assert {
    condition     = alltrue([for r in aws_ecr_repository.app : r.image_tag_mutability == "IMMUTABLE"])
    error_message = "Release tags must be immutable"
  }
}
