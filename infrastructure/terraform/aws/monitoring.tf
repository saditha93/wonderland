resource "aws_cloudwatch_log_group" "app" {
  name              = "/wonderland/${local.name}/application"
  retention_in_days = 7
}
