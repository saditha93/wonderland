mock_provider "aws" {}
run "offline_security_plan" {
  command = plan
  variables {
    account_id   = "111111111111"
    region       = "us-east-1"
    stage        = "offline-test"
    state_bucket = "wonderland-offline-test-state"
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.state.block_public_policy
    error_message = "Public access must be blocked"
  }
  assert {
    condition     = aws_s3_bucket.state.force_destroy == false
    error_message = "State deletion must not empty the bucket"
  }
}
