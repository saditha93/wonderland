module "network" {
  source = "../modules/network"
  name   = var.name
  azs    = var.azs
}

module "queue" {
  source = "../modules/queue"
  name   = var.name
}

locals {
  service_trust = { Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "eks.amazonaws.com" }, Action = "sts:AssumeRole" }] }
  node_trust    = { Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }] }
  oidc_host     = replace(aws_eks_cluster.demo.identity[0].oidc[0].issuer, "https://", "")
}

resource "aws_iam_role" "cluster" {
  name               = "${var.name}-cluster"
  assume_role_policy = jsonencode(local.service_trust)
}

resource "aws_iam_role_policy_attachment" "cluster" {
  role       = aws_iam_role.cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

resource "aws_kms_key" "secrets" {
  description             = "${var.name} Kubernetes secret envelope encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true
}

resource "aws_eks_cluster" "demo" {
  name     = var.name
  role_arn = aws_iam_role.cluster.arn
  version  = var.eks_version
  access_config {
    authentication_mode                         = "API"
    bootstrap_cluster_creator_admin_permissions = false
  }

  vpc_config {
    subnet_ids              = concat(module.network.public_subnets, module.network.private_subnets)
    endpoint_private_access = true
    endpoint_public_access  = true
    public_access_cidrs     = [var.operator_cidr]
  }

  encryption_config {
    resources = ["secrets"]
    provider {
      key_arn = aws_kms_key.secrets.arn
    }
  }

  upgrade_policy { support_type = "STANDARD" }
  enabled_cluster_log_types = ["api", "audit", "authenticator", "controllerManager", "scheduler"]
  depends_on                = [aws_iam_role_policy_attachment.cluster, aws_cloudwatch_log_group.eks, aws_iam_role_policy.cluster_encryption]
}

resource "aws_cloudwatch_log_group" "eks" {
  name              = "/aws/eks/${var.name}/cluster"
  retention_in_days = 7
}

resource "aws_eks_access_entry" "operator" {
  cluster_name  = aws_eks_cluster.demo.name
  principal_arn = var.operator_role_arn
  type          = "STANDARD"
}

resource "aws_eks_access_policy_association" "operator" {
  cluster_name  = aws_eks_cluster.demo.name
  principal_arn = var.operator_role_arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  access_scope {
    type = "cluster"
  }

  depends_on = [aws_eks_access_entry.operator]
}

resource "aws_iam_role" "node" {
  name               = "${var.name}-node"
  assume_role_policy = jsonencode(local.node_trust)
}

resource "aws_iam_role_policy_attachment" "node" {
  for_each   = toset(["AmazonEKSWorkerNodePolicy", "AmazonEC2ContainerRegistryPullOnly", "AmazonEKS_CNI_Policy"])
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/${each.key}"
}

resource "aws_launch_template" "node" {
  name_prefix = "${var.name}-"
  tag_specifications {
    resource_type = "instance"
    tags          = { Project = "wonderland", Name = var.name, Stage = var.stage }
  }
  tag_specifications {
    resource_type = "volume"
    tags          = { Project = "wonderland", Name = var.name, Stage = var.stage }
  }
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = 20
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }
}

resource "aws_eks_node_group" "demo" {
  cluster_name    = aws_eks_cluster.demo.name
  node_group_name = "demo"
  node_role_arn   = aws_iam_role.node.arn
  subnet_ids      = module.network.public_subnets
  ami_type        = "AL2023_ARM_64_STANDARD"
  instance_types  = [var.node_instance_type]
  capacity_type   = "ON_DEMAND"
  scaling_config {
    desired_size = 2
    min_size     = 2
    max_size     = 3
  }

  launch_template {
    id      = aws_launch_template.node.id
    version = aws_launch_template.node.latest_version
  }

  update_config {
    max_unavailable = 1
  }

  depends_on = [aws_iam_role_policy_attachment.node]
}

resource "aws_security_group" "db" {
  name   = "${var.name}-db"
  vpc_id = module.network.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "db" {
  security_group_id            = aws_security_group.db.id
  referenced_security_group_id = aws_eks_cluster.demo.vpc_config[0].cluster_security_group_id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

resource "aws_db_subnet_group" "demo" {
  name       = var.name
  subnet_ids = module.network.private_subnets
}

resource "aws_db_parameter_group" "tls" {
  name_prefix = "${var.name}-"
  family      = "postgres17"
  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = "immediate"
  }
}

resource "aws_db_instance" "demo" {
  identifier                  = var.name
  engine                      = "postgres"
  engine_version              = var.rds_engine_version
  instance_class              = var.db_instance_class
  allocated_storage           = 20
  storage_type                = "gp3"
  storage_encrypted           = true
  db_name                     = "wonderland"
  username                    = "wonderland_owner"
  manage_master_user_password = true
  publicly_accessible         = false
  multi_az                    = false
  db_subnet_group_name        = aws_db_subnet_group.demo.name
  vpc_security_group_ids      = [aws_security_group.db.id]
  parameter_group_name        = aws_db_parameter_group.tls.name
  backup_retention_period     = 0
  skip_final_snapshot         = !var.retain_final_snapshot
  final_snapshot_identifier   = "${var.name}-${var.final_snapshot_suffix}"
  delete_automated_backups    = true
  deletion_protection         = !var.allow_database_destroy
  auto_minor_version_upgrade  = false
}

resource "aws_secretsmanager_secret" "runtime" {
  name_prefix             = "${var.name}-runtime-"
  recovery_window_in_days = 7
}

resource "aws_iam_openid_connect_provider" "eks" {
  url            = aws_eks_cluster.demo.identity[0].oidc[0].issuer
  client_id_list = ["sts.amazonaws.com"]
}

resource "aws_iam_role" "analytics" {
  name               = "${var.name}-analytics"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Federated = aws_iam_openid_connect_provider.eks.arn }, Action = "sts:AssumeRoleWithWebIdentity", Condition = { StringEquals = { "${local.oidc_host}:sub" = "system:serviceaccount:wonderland:analytics-worker", "${local.oidc_host}:aud" = "sts.amazonaws.com" } } }] })
}

resource "aws_iam_role_policy" "analytics" {
  role   = aws_iam_role.analytics.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"], Resource = module.queue.arn }] })
}

resource "aws_iam_role" "alb" {
  name               = "${var.name}-alb"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Federated = aws_iam_openid_connect_provider.eks.arn }, Action = "sts:AssumeRoleWithWebIdentity", Condition = { StringEquals = { "${local.oidc_host}:sub" = "system:serviceaccount:kube-system:aws-load-balancer-controller", "${local.oidc_host}:aud" = "sts.amazonaws.com" } } }] })
}

resource "aws_iam_role_policy" "alb" {
  role   = aws_iam_role.alb.id
  policy = file("${path.module}/alb-controller-iam.json")
}

resource "aws_sns_topic" "alerts" {
  name = "${var.name}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

resource "aws_cloudwatch_metric_alarm" "dead" {
  alarm_name          = "${var.name}-dead-events"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = "${var.name}-events-dead" }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

output "cluster_name" {
  value = aws_eks_cluster.demo.name
}

output "vpc_id" {
  value = module.network.vpc_id
}

output "private_subnets" {
  value = module.network.private_subnets
}

output "node_security_group" {
  value = aws_eks_cluster.demo.vpc_config[0].cluster_security_group_id
}

output "db_endpoint" {
  value = aws_db_instance.demo.address
}

output "db_master_secret_arn" {
  value = aws_db_instance.demo.master_user_secret[0].secret_arn
}

output "runtime_secret_arn" {
  value = aws_secretsmanager_secret.runtime.arn
}

output "queue_url" {
  value = module.queue.url
}

output "dead_queue_url" {
  value = module.queue.dead_url
}

output "analytics_role_arn" {
  value = aws_iam_role.analytics.arn
}

output "alb_role_arn" {
  value = aws_iam_role.alb.arn
}

resource "aws_iam_role_policy" "analytics_dlq_status" {
  role   = aws_iam_role.analytics.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["sqs:GetQueueAttributes"], Resource = module.queue.dead_arn }] })
}
resource "aws_cloudwatch_metric_alarm" "lag" {
  alarm_name          = "${var.name}-event-lag"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateAgeOfOldestMessage"
  dimensions          = { QueueName = "${var.name}-events" }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 120
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}
resource "aws_iam_role_policy" "cluster_encryption" {
  role   = aws_iam_role.cluster.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["kms:Encrypt", "kms:Decrypt", "kms:DescribeKey", "kms:CreateGrant"], Resource = aws_kms_key.secrets.arn }] })
}
resource "aws_security_group" "alb" {
  name   = "${var.name}-alb"
  vpc_id = module.network.vpc_id
}
resource "aws_vpc_security_group_egress_rule" "alb_targets" {
  security_group_id            = aws_security_group.alb.id
  referenced_security_group_id = aws_eks_cluster.demo.vpc_config[0].cluster_security_group_id
  from_port                    = 8443
  to_port                      = 8443
  ip_protocol                  = "tcp"
}
resource "aws_vpc_security_group_ingress_rule" "frontend_targets" {
  security_group_id            = aws_eks_cluster.demo.vpc_config[0].cluster_security_group_id
  referenced_security_group_id = aws_security_group.alb.id
  from_port                    = 8443
  to_port                      = 8443
  ip_protocol                  = "tcp"
}
output "alb_security_group_id" { value = aws_security_group.alb.id }
resource "aws_cloudwatch_log_group" "application" {
  name              = "/wonderland/${var.name}/application"
  retention_in_days = 7
}
resource "aws_iam_role" "logs" {
  name               = "${var.name}-logs"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Federated = aws_iam_openid_connect_provider.eks.arn }, Action = "sts:AssumeRoleWithWebIdentity", Condition = { StringEquals = { "${local.oidc_host}:sub" = "system:serviceaccount:kube-system:wonderland-logs", "${local.oidc_host}:aud" = "sts.amazonaws.com" } } }] })
}
resource "aws_iam_role_policy" "logs" {
  role   = aws_iam_role.logs.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"], Resource = [aws_cloudwatch_log_group.application.arn, "${aws_cloudwatch_log_group.application.arn}:*"] }] })
}
output "application_log_group" { value = aws_cloudwatch_log_group.application.name }
output "logs_role_arn" { value = aws_iam_role.logs.arn }
