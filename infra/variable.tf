variable "aws_region" {
  description = "AWS region"
}

variable "instance_type" {
  description = "EC2 instance type"
}

variable "key_name" {
  description = "Name of the SSH key pair"
}

variable "cidr_blocks" {
  description = "List of CIDR blocks for security group ingress"
  type        = list(string)
}

variable "my_ip_address" {
  description = "Your public IP address"
}