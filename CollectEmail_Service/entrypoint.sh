#!/bin/bash
set -e

echo "Starting email collector container..."

# Export environment variables to a file for cron to use (with proper quoting)
echo "Exporting environment variables for cron..."
{
    [ -n "${GMAIL_EMAIL:-}" ] && printf "export GMAIL_EMAIL=%q\n" "$GMAIL_EMAIL"
    [ -n "${GMAIL_APP_PASSWORD:-}" ] && printf "export GMAIL_APP_PASSWORD=%q\n" "$GMAIL_APP_PASSWORD"
    [ -n "${AWS_REGION:-}" ] && printf "export AWS_REGION=%q\n" "$AWS_REGION"
    [ -n "${S3_BUCKET:-}" ] && printf "export S3_BUCKET=%q\n" "$S3_BUCKET"
    [ -n "${S3_PREFIX:-}" ] && printf "export S3_PREFIX=%q\n" "$S3_PREFIX"
    [ -n "${OUTPUT_DIR:-}" ] && printf "export OUTPUT_DIR=%q\n" "$OUTPUT_DIR"
} > /app/cron-env

# Apply crontab from mounted volume
if [ -f /app/crontab ]; then
    echo "Applying crontab from mounted file..."
    # Remove user field if present (crontab command doesn't need it)
    sed 's/^\([^#]*\) root /\1 /' /app/crontab > /tmp/crontab-processed || cp /app/crontab /tmp/crontab-processed
    crontab /tmp/crontab-processed
    echo "Crontab applied successfully"
else
    echo "Warning: /app/crontab not found. Cron jobs will not be scheduled."
fi

# Run immediately on container start (don't exit container if it fails)
echo "Running email collection on startup..."
/app/run_email_and_upload.sh >> /var/log/cron.log 2>&1 || echo "Warning: Initial run failed, but continuing to start cron..."

# Start cron daemon
echo "Starting cron daemon..."
cron

# Tail cron log to keep container running and show output
echo "Tailing cron log..."
tail -f /var/log/cron.log

