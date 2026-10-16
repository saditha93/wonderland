mock_provider "aws" {}
variables {
  account_id           = "111111111111"
  existing_policies    = []
  existing_attachments = []
  documents = { for name in ["WonderlandDemoCompute", "WonderlandDemoServices", "WonderlandDemoAccess", "WonderlandDemoDependencies", "WonderlandRuntimeBoundary"] : name => jsonencode({
    Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "s3:GetObject", Resource = "arn:aws:s3:::offline-demo/*" }]
  }) }
  descriptions = { for name in ["WonderlandDemoCompute", "WonderlandDemoServices", "WonderlandDemoAccess", "WonderlandDemoDependencies", "WonderlandRuntimeBoundary"] : name => "Offline policy" }
}
run "non_root_grants" {
  command = plan
  assert {
    condition     = length(aws_iam_policy.definition) == 5
    error_message = "Manage only the five reviewed definitions."
  }
  assert {
    condition     = length(aws_iam_user_policy_attachment.deployment) == 4 && !contains(keys(aws_iam_user_policy_attachment.deployment), "WonderlandRuntimeBoundary")
    error_message = "The server boundary must never be attached to the deployment user."
  }
  assert {
    condition     = alltrue([for attachment in aws_iam_user_policy_attachment.deployment : attachment.user == "wonderland"])
    error_message = "Never attach grants to another identity."
  }
}
