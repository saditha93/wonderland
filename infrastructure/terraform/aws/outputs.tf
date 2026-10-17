output "deployment" {
  value = {
    instance_id        = aws_instance.demo.id
    server_name        = var.server_name
    ssh_key_name       = data.aws_key_pair.ssh.key_name
    ssh_allowed_cidr   = var.ssh_allowed_cidr
    server_ip          = aws_eip.demo.public_ip
    artifact_bucket    = aws_s3_bucket.artifacts.id
    runtime_secret_arn = aws_secretsmanager_secret.runtime.arn
    pool_id            = aws_cognito_user_pool.visitors.id
    client_id          = aws_cognito_user_pool_client.web.id
    api_url            = aws_apigatewayv2_api.demo.api_endpoint
    queue_url          = aws_sqs_queue.events.url
    dead_queue_url     = aws_sqs_queue.dead.url
    repositories       = { for k, v in aws_ecr_repository.app : k => v.repository_url }
    portals            = { for k, v in aws_amplify_app.portal : k => { app_id = v.id, origin = "https://demo.${v.default_domain}" } }
  }
}

output "ssh_command" {
  description = "Run on your laptop; keep the private PEM on that laptop."
  value       = "ssh -i ~/Projects/pem/sliit_test.pem ubuntu@${aws_eip.demo.public_ip}"
}
