variable "name" {
  type = string
}

resource "aws_sqs_queue" "dead" {
  name                      = "${var.name}-events-dead"
  sqs_managed_sse_enabled   = true
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "events" {
  name                       = "${var.name}-events"
  sqs_managed_sse_enabled    = true
  visibility_timeout_seconds = 60
  receive_wait_time_seconds  = 1
  message_retention_seconds  = 345600
  redrive_policy             = jsonencode({ deadLetterTargetArn = aws_sqs_queue.dead.arn, maxReceiveCount = 3 })
}

resource "aws_sqs_queue_redrive_allow_policy" "dead" {
  queue_url            = aws_sqs_queue.dead.url
  redrive_allow_policy = jsonencode({ redrivePermission = "byQueue", sourceQueueArns = [aws_sqs_queue.events.arn] })
}

resource "aws_sqs_queue_policy" "tls" {
  queue_url = aws_sqs_queue.events.url
  policy    = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Deny", Principal = "*", Action = "sqs:*", Resource = aws_sqs_queue.events.arn, Condition = { Bool = { "aws:SecureTransport" = "false" } } }] })
}

output "url" {
  value = aws_sqs_queue.events.url
}

output "arn" {
  value = aws_sqs_queue.events.arn
}

output "dead_url" {
  value = aws_sqs_queue.dead.url
}

output "dead_arn" {
  value = aws_sqs_queue.dead.arn
}

