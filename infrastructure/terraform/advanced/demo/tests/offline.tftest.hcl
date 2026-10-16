mock_provider "aws" {}
run "offline_security_plan" {
  command = plan
  variables {
    account_id         = "111111111111"
    region             = "us-east-1"
    stage              = "offline-test"
    azs                = ["us-east-1a", "us-east-1b"]
    operator_cidr      = "203.0.113.1/32"
    operator_role_arn  = "arn:aws:iam::111111111111:role/offline-operator"
    eks_version        = "1.35"
    rds_engine_version = "17.7"
    frontend_origin    = "https://demo.example.com"
    alarm_email        = "offline@example.com"
  }
  assert {
    condition     = aws_eks_cluster.demo.upgrade_policy[0].support_type == "STANDARD"
    error_message = "Extended support charges must not be enabled silently"
  }
  assert {
    condition     = aws_db_instance.demo.publicly_accessible == false && aws_db_instance.demo.storage_encrypted
    error_message = "DB must remain private and encrypted"
  }
  assert {
    condition     = aws_db_instance.demo.deletion_protection && !aws_db_instance.demo.skip_final_snapshot
    error_message = "DB destroy must require an explicit protection change"
  }
  assert {
    condition     = aws_launch_template.node.metadata_options[0].http_tokens == "required" && aws_launch_template.node.metadata_options[0].http_put_response_hop_limit == 1
    error_message = "Pods must not inherit node credentials"
  }
  assert {
    condition     = aws_eks_node_group.demo.scaling_config[0].desired_size == 2
    error_message = "Two workers are required for the demo topology"
  }
}
