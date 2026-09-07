# 💳 FinPulze Global Payments

**Secure CI/CD, Infrastructure Automation & Disaster Recovery**

Welcome to the FinPulze Payments infrastructure project! This repository contains the source code, deployment pipelines, and Infrastructure as Code (IaC) necessary to build a secure, highly resilient transaction engine on AWS.

## 📖 Project Overview
FinPulze is a high-growth FinTech firm processing multi-currency transactions. Following a severe outage and a security audit that revealed exposed containers and hardcoded secrets, the engineering team is rebuilding the architecture from scratch. 

Your mission is to migrate this manual, risk-prone environment into a **Fully Automated Continuous Deployment (CD) Pipeline** with a zero-trust network topology and automated disaster recovery.

### The Objectives:
1. **Infrastructure as Code:** Provision AWS EC2, S3, and CloudWatch automatically using Terraform.
2. **Container Security:** Deploy the FinPulze API and a PostgreSQL database using Docker, binding them securely to `127.0.0.1` to block public internet access.
3. **Secure Ingress:** Set up an Nginx reverse proxy with a free Certbot (Let's Encrypt) SSL certificate on a custom DuckDNS domain.
4. **DevSecOps & CI/CD:** Build a GitHub Actions pipeline that scans your code for critical vulnerabilities (Aqua Trivy) and automatically deploys passing code to the EC2 server via remote SSH.
5. **Disaster Recovery:** Automate timestamped database backups to Amazon S3 using a Bash script and a Linux 12-hour Cronjob.

---

## 🛠️ Technology Stack
* **Cloud Provider:** AWS (EC2, S3, IAM, CloudWatch)
* **Infrastructure Automation:** Terraform
* **Containerization:** Docker
* **Web Server / Proxy:** Nginx
* **Security & SSL:** Aqua Trivy, Let's Encrypt (Certbot)
* **CI/CD Pipeline:** GitHub Actions (SCP & Remote SSH)
* **Scripting:** Linux Bash, Cron

---

## 📂 Project File Structure
To keep the project organized, ensure your repository follows this standard directory structure:

```text
finpulze-payments/
├── .github/
│   └── workflows/
│       └── deploy.yml          # GitHub Actions pipeline (Trivy, SCP, SSH)
├── app/
│   ├── main.py                 # FastAPI Application Code
│   ├── requirements.txt        # Python Dependencies
│   └── Dockerfile              # Instructions to containerize the app
├── infra/
│   ├── main.tf                 # Terraform code (EC2, S3, IAM, Security Groups)
│   ├── variables.tf            # Terraform variables
│   └── user_data.sh            # EC2 Bootstrap script (Installs Docker, Nginx, AWS CLI)
├── scripts/
│   └── backup.sh               # Bash script for pg_dump and S3 upload
├── .env.example                # Example of required environment variables (NO REAL SECRETS)
├── .gitignore                  # Ignores venv, .env, and Terraform state files
└── README.md                   # Project documentation
```




## 🚀 Execution Phases

### Phase 1: Infrastructure Provisioning (Terraform)
Navigate to the `/infra` folder. You will write Terraform code to provision an AWS EC2 instance. Use the `user_data.sh` script to automatically install Docker, Nginx, and the AWS CLI when the server first boots. *Verify success by SSHing into the server and checking that Docker is installed.*

### Phase 2: Local Server Configuration (Security & SSL)

1. SSH into your newly created EC2 instance.
2. Create an `.env` file on the server to securely store your `DATABASE_URL` and `PAYMENT_GATEWAY_SECRET`. **Never commit this file to GitHub.**
3. Run your PostgreSQL and FastAPI Docker containers. **Crucial Step:** Bind both containers to `127.0.0.1` so they are completely hidden from the public internet.
4. Point a DuckDNS domain to your EC2 Public IP.
5. Configure Nginx to proxy traffic to your internal application port, and secure it using Certbot.

### Phase 3: Disaster Recovery Automation

1. Use Terraform to create an Amazon S3 bucket and an IAM Instance Profile (giving EC2 permission to write to S3).
2. Write the `backup.sh` script to execute a `pg_dump` of your Dockerized database, tagging the output file with a dynamic timestamp (e.g., `backup_2026-09-04_1200.sql`).
3. Schedule the script using `crontab -e` to run automatically every 12 hours.

### Phase 4: True Continuous Deployment (GitHub Actions)
Build a fully automated pipeline in `.github/workflows/deploy.yml` that triggers on every push to the `main` branch:

1. **Security Scan:** Run an Aqua Trivy scan on the Docker image. If "CRITICAL" vulnerabilities are found, fail the build.
2. **File Transfer:** Use an SCP action to copy the latest code securely to the EC2 server.
3. **Zero-Downtime Deployment:** Use an SSH action to remotely log into the EC2 server, stop the old container, build the new Docker image, and start the new container using the server's `.env` file.

## ⚠️ Critical Security Rules

- **Never commit your `.env` file or AWS Access Keys to GitHub.** Always use AWS IAM Roles for EC2-to-S3 authentication.
- **Do not expose Port 8000 in your AWS Security Groups.** All public web traffic must flow through Port 80/443 (Nginx), which will safely proxy the traffic internally to your Docker containers.
- **Store SSH Keys securely.** When setting up the GitHub Actions pipeline, your EC2 SSH private key must be stored in **GitHub Repository Secrets**, nowhere else.