variable "name" {
  type = string
}

variable "azs" {
  type = list(string)
}

resource "aws_vpc" "demo" {
  cidr_block           = "10.60.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
}

resource "aws_internet_gateway" "demo" {
  vpc_id = aws_vpc.demo.id
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.demo.id
  availability_zone       = var.azs[count.index]
  cidr_block              = cidrsubnet(aws_vpc.demo.cidr_block, 8, count.index)
  map_public_ip_on_launch = true
  tags                    = { "kubernetes.io/role/elb" = "1", "kubernetes.io/cluster/${var.name}" = "shared" }
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.demo.id
  availability_zone = var.azs[count.index]
  cidr_block        = cidrsubnet(aws_vpc.demo.cidr_block, 8, count.index + 10)
  tags              = { "kubernetes.io/role/internal-elb" = "1", "kubernetes.io/cluster/${var.name}" = "shared" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.demo.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.demo.id
  }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

output "vpc_id" {
  value = aws_vpc.demo.id
}

output "public_subnets" {
  value = aws_subnet.public[*].id
}

output "private_subnets" {
  value = aws_subnet.private[*].id
}

