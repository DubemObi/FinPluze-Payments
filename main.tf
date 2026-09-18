terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  required_version = ">= 1.5.0"
}

provider "aws" {
  region = "eu-west-2"
}

# -------------------------
# VPC
# -------------------------

resource "aws_vpc" "main_network" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name      = "dev-environment"
    ManagedBy = "Terraform"
  }
}

# -------------------------
# Internet Gateway
# -------------------------

resource "aws_internet_gateway" "main_gateway" {
  vpc_id = aws_vpc.main_network.id

  tags = {
    Name      = "dev-internet-gateway"
    ManagedBy = "Terraform"
  }
}

# -------------------------
# Subnet
# -------------------------

resource "aws_subnet" "public_subnet" {
  vpc_id                  = aws_vpc.main_network.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "eu-west-2a"
  map_public_ip_on_launch = true

  tags = {
    Name      = "dev-public-subnet"
    ManagedBy = "Terraform"
  }
}

# -------------------------
# Route Table
# -------------------------

resource "aws_route_table" "public_route_table" {
  vpc_id = aws_vpc.main_network.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main_gateway.id
  }

  tags = {
    Name      = "dev-public-route-table"
    ManagedBy = "Terraform"
  }
}

# -------------------------
# Route Table Association
# -------------------------

resource "aws_route_table_association" "public_subnet_association" {
  subnet_id      = aws_subnet.public_subnet.id
  route_table_id = aws_route_table.public_route_table.id
}

# -------------------------
# Security Group
# -------------------------

resource "aws_security_group" "web_security_group" {
  name        = "dev-web-security-group"
  description = "Allow HTTP, HTTPS and SSH traffic"
  vpc_id      = aws_vpc.main_network.id

  # SSH
  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # HTTP
  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # HTTPS
  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Outbound traffic
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name      = "dev-web-security-group"
    ManagedBy = "Terraform"
  }
}

# -------------------------
# Ubuntu AMI
# -------------------------

data "aws_ami" "ubuntu" {
  most_recent = true

  owners = ["099720109477"]

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "root-device-type"
    values = ["ebs"]
  }
}

# -------------------------
# EC2 Instance
# -------------------------

resource "aws_instance" "ubuntu_server" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = "t3.micro"
  key_name      = "dev-ubuntu-key"

  subnet_id = aws_subnet.public_subnet.id

  vpc_security_group_ids = [
    aws_security_group.web_security_group.id
  ]

  iam_instance_profile = aws_iam_instance_profile.ec2_s3_profile.name

  tags = {
    Name      = "dev-ubuntu-server"
    ManagedBy = "Terraform"
  }
}

# -------------------------
# S3 Backup Bucket
# -------------------------

resource "aws_s3_bucket" "backup" {
  bucket = "dev-finpulze-backup-dubem"

  tags = {
    Name      = "dev-finpulze-backup"
    ManagedBy = "Terraform"
  }
}

# -------------------------
# IAM Role for EC2 S3 Access
# -------------------------

resource "aws_iam_role" "ec2_s3_role" {
  name = "dev-ec2-s3-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

# -------------------------
# S3 Write Policy
# -------------------------

resource "aws_iam_role_policy" "ec2_s3_write" {
  name = "dev-ec2-s3-write"
  role = aws_iam_role.ec2_s3_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject"
        ]
        Resource = "${aws_s3_bucket.backup.arn}/*"
      }
    ]
  })
}

# -------------------------
# EC2 Instance Profile
# -------------------------

resource "aws_iam_instance_profile" "ec2_s3_profile" {
  name = "dev-ec2-s3-profile"
  role = aws_iam_role.ec2_s3_role.name
}


# -------------------------
# CloudWatch CPU Alarm
# -------------------------

resource "aws_cloudwatch_metric_alarm" "high_cpu" {
  alarm_name        = "dev-ubuntu-high-cpu"
  alarm_description = "Alarm when EC2 CPU utilization exceeds 80%"

  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 300
  statistic           = "Average"
  threshold           = 80

  dimensions = {
    InstanceId = aws_instance.ubuntu_server.id
  }

  alarm_actions = []
  ok_actions    = []
}

# -------------------------
# Outputs
# -------------------------

output "vpc_id" {
  value = aws_vpc.main_network.id
}

output "instance_id" {
  value = aws_instance.ubuntu_server.id
}

output "instance_public_ip" {
  value = aws_instance.ubuntu_server.public_ip
}