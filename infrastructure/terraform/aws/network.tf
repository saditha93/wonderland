resource "aws_vpc" "demo" {
  cidr_block           = "10.70.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
}

resource "aws_subnet" "demo" {
  vpc_id            = aws_vpc.demo.id
  cidr_block        = "10.70.1.0/24"
  availability_zone = var.availability_zone
}

resource "aws_internet_gateway" "demo" { vpc_id = aws_vpc.demo.id }

resource "aws_route_table" "demo" {
  vpc_id = aws_vpc.demo.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.demo.id
  }
}

resource "aws_route_table_association" "demo" {
  subnet_id      = aws_subnet.demo.id
  route_table_id = aws_route_table.demo.id
}

resource "aws_security_group" "demo" {
  name        = local.name
  description = "HTTPS API and ACME; SSH restricted to operator IPv4; SSM retained"
  vpc_id      = aws_vpc.demo.id
  ingress {
    description = "Public ACME HTTP-01 challenge only"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "TLS API; origin token and application authorization required"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "Laptop SSH only"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_allowed_cidr]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_network_interface" "demo" {
  subnet_id       = aws_subnet.demo.id
  security_groups = [aws_security_group.demo.id]
}

resource "aws_sqs_queue" "dead" {
  name                      = "${local.name}-dead"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "events" {
  name                       = "${local.name}-events"
  visibility_timeout_seconds = 30
  sqs_managed_sse_enabled    = true
  redrive_policy             = jsonencode({ deadLetterTargetArn = aws_sqs_queue.dead.arn, maxReceiveCount = 5 })
}
