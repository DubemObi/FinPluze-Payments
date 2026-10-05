
#!/bin/bash
# Exit immediately if a command exits with a non-zero status
set -e

# Update and install dependencies
apt-get update -y
apt-get install -y nginx unzip curl

# Install AWS CLI into a safe directory
cd /tmp
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip -o awscliv2.zip
./aws/install

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Configure Docker permissions
usermod -aG docker ubuntu
systemctl enable docker
systemctl start docker



