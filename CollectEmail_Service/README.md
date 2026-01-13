# Email Collection Service

Automated service that collects unread emails from Gmail IMAP and uploads them to AWS S3 on a scheduled basis. The service runs every 2 hours via cron, extracts email metadata, body content, and attachments, then syncs the data to S3.

## Overview

This service is designed to run as a Docker container that:
- Connects to Gmail via IMAP
- Fetches unread emails from the INBOX
- Extracts email metadata, body text, and attachments
- Saves raw email files (.eml format) and metadata JSON
- Uploads collected data to AWS S3
- Marks processed emails as read
- Runs automatically every 2 hours via cron

## Features

- **Automated Collection**: Scheduled email collection every 2 hours using cron
- **Gmail IMAP Integration**: Connects to Gmail using application-specific passwords
- **Email Processing**: Extracts metadata (sender, subject, date), body text, and attachments
- **Raw Email Storage**: Preserves original .eml files for archival purposes
- **S3 Integration**: Automatic upload to AWS S3 bucket
- **IAM Role Support**: Works with EC2 IAM roles for secure AWS access (recommended)
- **Persistent Logging**: Execution logs saved to mounted volume
- **Health Monitoring**: Container health check for cron daemon status

## Architecture

### Components

- **gmail.py**: Main Python script that handles Gmail IMAP connection, email fetching, parsing, and local file storage
- **run_email_and_upload.sh**: Shell script that orchestrates email collection and S3 upload
- **entrypoint.sh**: Container initialization script that sets up cron and environment variables
- **crontab**: Cron schedule configuration (runs every 2 hours)
- **Dockerfile**: Container image definition with Python, cron, and AWS CLI
- **docker-compose.yml**: Container orchestration configuration

### Data Flow

1. **Email Collection**: 
   - Service connects to Gmail IMAP server (imap.gmail.com:993)
   - Searches for unread emails in INBOX
   - Fetches full email content (RFC822 format)

2. **Local Processing**:
   - Parses email headers (From, Subject, Date)
   - Extracts body text (prefers text/plain, falls back to HTML-to-text conversion)
   - Downloads attachments to local filesystem
   - Saves raw .eml files with timestamped prefixes
   - Generates emails.json with metadata and email records

3. **S3 Upload**:
   - Uploads emails.json to S3 (overwrites existing)
   - Syncs raw_emails/ directory to S3 (incremental)
   - Attachments remain local only (not synced to S3)

4. **Cleanup**:
   - Deletes local emails.json after successful S3 upload
   - Deletes local raw_emails/ directory after successful S3 sync
   - Attachments directory persists locally

5. **Email Status**:
   - Processed emails are marked as read (\\Seen flag)

## Data Interface

### Input

- **Gmail Credentials**: Email address and application-specific password
- **AWS Configuration**: Region, S3 bucket name, and S3 prefix path
- **Cron Schedule**: Execution frequency (default: every 2 hours)

### Output Structure

#### Local Filesystem (Temporary)

- `emails.json`: Email metadata JSON file (deleted after S3 upload)
- `raw_emails/`: Directory containing raw .eml files (deleted after S3 sync)
  - Format: `msg{timestamp}_{index:04d}.eml`
- `attachments/`: Directory containing email attachments (persists locally)
  - Format: `{prefix}_{index:02d}_{filename}`
- `logs/cron_{timestamp}.log`: Execution logs

#### S3 Structure

- `s3://{S3_BUCKET}/{S3_PREFIX}/emails.json`: Latest email metadata JSON
- `s3://{S3_BUCKET}/{S3_PREFIX}/raw_emails/`: Historical raw email files

#### Email Metadata JSON Format

```json
{
  "generated_at": "ISO8601 UTC timestamp",
  "count": "number of emails",
  "emails": [
    {
      "imap_id": "email message ID",
      "from_raw": "decoded From header",
      "sender_email": "sender email address",
      "subject": "email subject",
      "date": "email date header",
      "body_text": "extracted body text",
      "attachments": [
        {
          "filename": "attachment filename",
          "path": "local file path",
          "content_type": "MIME content type",
          "size": "file size in bytes"
        }
      ]
    }
  ]
}
```

## Prerequisites

- Docker and Docker Compose installed
- Gmail account with:
  - IMAP enabled
  - Application-specific password generated (16 characters)
- AWS account with:
  - S3 bucket created
  - IAM role with S3 permissions (for EC2 deployment, recommended)
  - Or AWS credentials configured (for local development)

## Configuration

### Environment Variables

Create a `.env` file in the `CollectEmail_Service` directory:

**Required:**
- `GMAIL_EMAIL`: Gmail email address
- `GMAIL_APP_PASSWORD`: Gmail application-specific password (16 characters)

**AWS Configuration:**
- `AWS_REGION`: AWS region (default: ap-southeast-1)
- `S3_BUCKET`: S3 bucket name (default: pipe-and-ro-email)
- `S3_PREFIX`: S3 prefix path (default: exports)

**Optional:**
- `OUTPUT_DIR`: Local output directory (default: /app/data)

### Cron Schedule

Edit `crontab` file to modify execution frequency:
- Default: `0 */2 * * *` (every 2 hours)
- Format: Standard cron syntax

## Deployment

### Local Development

1. Create `.env` file with required environment variables
2. Build and start container:
   ```bash
   docker-compose up -d
   ```
3. View logs:
   ```bash
   docker-compose logs -f email-collector
   ```

### AWS EC2 Deployment (Recommended)

#### IAM Role Setup

1. Create IAM Role:
   - Trust entity: EC2
   - Attach policy with S3 permissions:
     - `s3:PutObject` on bucket and objects
     - `s3:GetObject` on bucket and objects
     - `s3:ListBucket` on bucket

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
├── .env                   # Environment variables (create manually)
├── .gitignore            # Git ignore rules
├── logs/                  # Persistent logs (created automatically)
└── data/                  # Optional: local data persistence
```

## Volume Mounts

- `./logs:/app/logs`: Persistent execution logs directory
- `./crontab:/app/crontab:ro`: Cron schedule file (read-only)
- `./data:/app/data`: Optional local data persistence (commented out by default)

## Monitoring

### Health Check

Container includes health check that monitors cron daemon process:
- Interval: 30 seconds
- Timeout: 10 seconds
- Retries: 3
- Start period: 5 seconds

### Logging

**Container Logs:**
- View with: `docker-compose logs -f email-collector`
- Shows container startup and cron daemon status

**Cron Execution Logs:**
- View with: `docker exec email-collector tail -f /var/log/cron.log`
- Shows cron job execution output

**Application Logs:**
- Location: `logs/cron_{timestamp}.log` on host filesystem
- Contains detailed execution logs for each run
- Includes email collection status, S3 upload results, and errors

## Troubleshooting

### Common Issues

**Missing Environment Variables**
- Verify `.env` file exists and contains all required variables
- Check container logs for environment variable errors

**Gmail IMAP Connection Failures**
- Verify Gmail app password is correct (16 characters)
- Ensure IMAP is enabled in Gmail settings
- Check network connectivity to imap.gmail.com:993

**AWS S3 Upload Failures**
- For EC2: Verify IAM role is attached to instance
- For local: Verify AWS credentials are configured
- Check IAM permissions include s3:PutObject, s3:GetObject, s3:ListBucket
- Verify S3 bucket name and region are correct

**Cron Not Running**
- Check cron daemon is running: `docker exec email-collector pgrep cron`
- Verify crontab file is mounted correctly
- Check cron logs: `docker exec email-collector tail -f /var/log/cron.log`

**No Emails Collected**
- Verify there are unread emails in Gmail INBOX
- Check if emails were already marked as read by previous runs
- Review application logs for IMAP search results

## Service Management

### Start Service
```bash
docker-compose up -d
```

### Stop Service
```bash
docker-compose down
```

### Restart Service
```bash
docker-compose restart email-collector
```

### View Logs
```bash
# Container logs
docker-compose logs -f email-collector

# Cron execution logs
docker exec email-collector tail -f /var/log/cron.log

# Application logs (on host)
ls -la logs/
tail -f logs/cron_*.log
```

### Manual Execution

To run email collection manually without waiting for cron:
```bash
docker exec email-collector /app/run_email_and_upload.sh
```

## File Relationships

- **entrypoint.sh** → Sets up cron and environment → Calls **run_email_and_upload.sh**
- **run_email_and_upload.sh** → Executes **gmail.py** → Uploads results to S3
- **gmail.py** → Connects to Gmail IMAP → Processes emails → Writes local files
- **crontab** → Defines schedule → Executes **run_email_and_upload.sh** via cron
- **docker-compose.yml** → Orchestrates container → Mounts volumes → Sets environment variables
- **Dockerfile** → Builds image → Installs dependencies → Sets up entrypoint

## Notes

- Emails are marked as read after processing (configurable in gmail.py)
- Attachments are saved locally but not synced to S3
- Raw .eml files are synced to S3 for archival purposes
- Local files (emails.json, raw_emails/) are deleted after successful S3 upload
- Logs persist across container restarts via volume mount
- Service runs immediately on container start, then follows cron schedule
