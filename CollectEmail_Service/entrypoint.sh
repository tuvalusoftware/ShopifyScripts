#!/bin/bash
set -e

echo "Starting email collector container..."

# Export environment variables to a file for cron to use
echo "Exporting environment variables for cron..."
env | grep -E '^(GMAIL_|AWS_|S3_|OUTPUT_DIR=)' > /app/cron-env || true

# Apply crontab from mounted volume
if [ -f /app/crontab ]; then
    echo "Applying crontab from mounted file..."
    cp /app/crontab /etc/cron.d/email-collector-cron
    chmod 0644 /etc/cron.d/email-collector-cron
    crontab /etc/cron.d/email-collector-cron
    echo "Crontab applied successfully"
else
    echo "Warning: /app/crontab not found. Cron jobs will not be scheduled."
fi

# Run immediately on container start
echo "Running email collection on startup..."
/app/run_email_and_upload.sh >> /var/log/cron.log 2>&1

# Start cron daemon
echo "Starting cron daemon..."
cron

# Tail cron log to keep container running and show output
echo "Tailing cron log..."
tail -f /var/log/cron.log

