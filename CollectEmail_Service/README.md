# Email Collection Service - Docker Deployment

This service automatically collects unread emails from Gmail IMAP and uploads them to AWS S3 on a scheduled basis (every 2 hours).

## Features

- Automated email collection every 2 hours using cron
- Collects unread emails from Gmail IMAP
- Extracts email metadata, body text, and attachments
- Uploads collected data to S3 bucket
- Persistent logs across container restarts
- IAM role support for EC2 deployment (recommended)

## Prerequisites

- Docker and Docker Compose installed
- Gmail account with application-specific password
- AWS account with S3 bucket (or EC2 instance with IAM role)
- For EC2 deployment: EC2 instance with IAM role attached (recommended)

## Quick Start

### 1. Configure Environment Variables

Create a `.env` file in the `CollectEmail_Service` directory:

```bash
# Gmail Configuration (Required)
GMAIL_EMAIL=your-email@gmail.com
GMAIL_APP_PASSWORD=your-16-character-app-password

# AWS Configuration
# When using IAM role on EC2, only AWS_REGION is needed
AWS_REGION=ap-southeast-1

# S3 Configuration
S3_BUCKET=pipe-and-ro-email
S3_PREFIX=exports
```

### 2. Build and Run

```bash
cd CollectEmail_Service
docker-compose up -d
```

### 3. View Logs

```bash
# Container logs
docker-compose logs -f email-collector

# Cron execution logs
docker exec email-collector tail -f /var/log/cron.log

# Application logs (on host)
ls -la logs/
```

## AWS EC2 Deployment with IAM Role

### Setup IAM Role

1. Create IAM Role in AWS Console:

   - Go to IAM → Roles → Create Role
   - Select "EC2" as trusted entity
   - Attach policy with S3 permissions:
     ```json
     {
       "Version": "2012-10-17",
       "Statement": [
         {
           "Effect": "Allow",
           "Action": ["s3:PutObject", "s3:GetObject", "s3:ListBucket"],
           "Resource": ["arn:aws:s3:::pipe-and-ro-email", "arn:aws:s3:::pipe-and-ro-email/*"]
         }
       ]
     }
     ```

2. Attach Role to EC2 Instance:

   - EC2 Console → Select instance → Actions → Security → Modify IAM role
   - Select the created IAM role
   - Apply changes

3. Deploy Container:
   - No AWS credentials needed in environment variables
   - Container automatically uses EC2 instance IAM role
   - Only set `AWS_REGION` environment variable

## Directory Structure

```
CollectEmail_Service/
├── Dockerfile              # Container image definition
├── docker-compose.yml      # Container orchestration
├── crontab                 # Cron schedule configuration
├── entrypoint.sh          # Container startup script
├── requirements.txt       # Python dependencies
├── gmail.py              # Email collection script
├── run_email_and_upload.sh # Main execution script
├── .env                   # Environment variables (create from .env.example)
├── logs/                  # Persistent logs (created automatically)
└── data/                  # Optional: local data persistence
```

## Volume Mounts

- **Logs**: `./logs:/app/logs` - Persistent execution logs
- **Data** (Optional): `./data:/app/data` - Local data persistence

## Output Structure

### Local Filesystem

- `/app/data/emails.json` - Email metadata JSON
- `/app/data/raw_emails/` - Raw .eml files
- `/app/data/attachments/` - Email attachments (local only)
- `/app/logs/cron_YYYYMMDD_HHMMSS.log` - Execution logs

### S3 Structure

- `s3://{S3_BUCKET}/{S3_PREFIX}/emails.json` - Latest email metadata
- `s3://{S3_BUCKET}/{S3_PREFIX}/raw_emails/` - Historical raw emails

Note: Attachments are stored locally only and not synced to S3.

## Monitoring

### Health Check

The container includes a health check that monitors the cron daemon process.

### Viewing Logs

- Container logs: `docker-compose logs -f email-collector`
- Cron logs: `docker exec email-collector tail -f /var/log/cron.log`
- Application logs: `ls -la logs/` on host filesystem

## Troubleshooting

- **Missing environment variables**: Check `.env` file exists and contains required variables
- **AWS credentials issues**: Verify IAM role is attached to EC2 instance (for EC2 deployments)
- **Gmail IMAP connection failures**: Check Gmail app password is correct and IMAP is enabled
- **S3 sync failures**: Verify IAM role has correct S3 permissions

## Stopping the Service

```bash
docker-compose down
```

## Restarting the Service

```bash
docker-compose restart email-collector
```
