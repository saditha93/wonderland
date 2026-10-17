# Reference the existing key pair; Terraform never reads or uploads the private PEM.
data "aws_key_pair" "ssh" {
  key_name = var.ssh_key_name
}

resource "aws_instance" "demo" {
  ami                         = var.ami_id
  instance_type               = var.instance_type
  key_name                    = data.aws_key_pair.ssh.key_name
  tags                        = { Name = var.server_name }
  iam_instance_profile        = aws_iam_instance_profile.demo.name
  user_data                   = var.bootstrap_script
  user_data_replace_on_change = true
  volume_tags                 = { Project = "wonderland", Stack = local.name, ManagedBy = "terraform" }
  primary_network_interface {
    network_interface_id = aws_network_interface.demo.id
  }
  root_block_device {
    encrypted             = true
    volume_size           = 30
    volume_type           = "gp3"
    delete_on_termination = true
  }
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
    instance_metadata_tags      = "disabled"
  }
  depends_on = [aws_iam_role_policy.runtime, aws_route_table_association.demo]
  lifecycle { prevent_destroy = true }
}

resource "aws_eip" "demo" { domain = "vpc" }

resource "aws_eip_association" "demo" {
  allocation_id        = aws_eip.demo.id
  network_interface_id = aws_network_interface.demo.id
  depends_on           = [aws_instance.demo]
}
