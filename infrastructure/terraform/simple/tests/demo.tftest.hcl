mock_provider "aws" {}
variables {
  account_id        = "111111111111"
  ami_id            = "ami-offline"
  availability_zone = "us-east-1a"
  bootstrap_script  = "#!/bin/bash\ntrue"
  runtime_policy    = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
  origin_token      = "offline-test-token-0123456789012345678901234567890123456789"
}
run "bounded_demo" {
  command = plan
  assert {
    condition     = aws_instance.demo.instance_type == "t4g.medium" && aws_instance.demo.metadata_options[0].http_tokens == "required" && aws_instance.demo.root_block_device[0].encrypted
    error_message = "Require bounded ARM compute, encrypted disk and IMDSv2."
  }
  assert {
    condition     = toset([for p in aws_security_group.demo.ingress : p.from_port]) == toset([80, 443])
    error_message = "SSH, database, Kubernetes and monitoring ports must not be public."
  }
  assert {
    condition     = aws_iam_role.demo.permissions_boundary == "arn:aws:iam::111111111111:policy/WonderlandRuntimeBoundary"
    error_message = "Node role must retain the reviewed permissions boundary."
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.artifacts.block_public_acls && aws_s3_bucket_public_access_block.artifacts.block_public_policy
    error_message = "Artifact bucket must remain private."
  }
  assert {
    condition     = aws_cognito_user_pool_client.web.generate_secret == false && aws_cognito_user_pool_client.web.access_token_validity == 15
    error_message = "Browser Cognito client must be public with short-lived access tokens."
  }
}
