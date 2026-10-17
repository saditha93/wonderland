mock_provider "aws" {}
mock_provider "aws" { alias = "api_stage" }
variables {
  ssh_allowed_cidr  = "203.0.113.10/32"
  ssh_key_name      = "sliit_test"
  server_name       = "Wonderland Demo Server"
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
    condition     = aws_instance.demo.instance_type == "m7i-flex.large" && aws_instance.demo.metadata_options[0].http_tokens == "required" && aws_instance.demo.root_block_device[0].encrypted
    error_message = "Require the reviewed Free-plan-eligible compute size, encrypted disk and IMDSv2."
  }
  assert {
    condition     = toset([for p in aws_security_group.demo.ingress : p.from_port]) == toset([22, 80, 443])
    error_message = "Only HTTPS, ACME and operator-scoped SSH are allowed; database/Kubernetes/monitoring stay private."
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

run "ssh_and_name" {
  command = plan
  assert {
    condition     = aws_instance.demo.key_name == "sliit_test" && aws_instance.demo.tags["Name"] == "Wonderland Demo Server"
    error_message = "Attach the existing SSH key and readable EC2 Name tag."
  }
  assert {
    condition     = alltrue([for rule in aws_security_group.demo.ingress : rule.from_port != 22 || (rule.to_port == 22 && rule.protocol == "tcp" && toset(rule.cidr_blocks) == toset(["203.0.113.10/32"]))])
    error_message = "SSH must be restricted to the single laptop IPv4 /32."
  }
}

run "reject_public_ssh" {
  command = plan
  variables { ssh_allowed_cidr = "0.0.0.0/0" }
  expect_failures = [var.ssh_allowed_cidr]
}
