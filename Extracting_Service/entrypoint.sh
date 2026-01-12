#!/bin/bash
set -e

echo "Starting S3 EML processor container..."

# Export environment variables to a file for cron to use (with proper quoting)
echo "Exporting environment variables for cron..."
{
    [ -n "${AWS_REGION:-}" ] && printf "export AWS_REGION=%q\n" "$AWS_REGION"
    [ -n "${AWS_ACCESS_KEY_ID:-}" ] && printf "export AWS_ACCESS_KEY_ID=%q\n" "$AWS_ACCESS_KEY_ID"
    [ -n "${AWS_SECRET_ACCESS_KEY:-}" ] && printf "export AWS_SECRET_ACCESS_KEY=%q\n" "$AWS_SECRET_ACCESS_KEY"
    [ -n "${S3_BUCKET:-}" ] && printf "export S3_BUCKET=%q\n" "$S3_BUCKET"
    [ -n "${S3_PREFIX:-}" ] && printf "export S3_PREFIX=%q\n" "$S3_PREFIX"
    [ -n "${OUTPUT_DIR:-}" ] && printf "export OUTPUT_DIR=%q\n" "$OUTPUT_DIR"
    [ -n "${OPENAI_API_KEY:-}" ] && printf "export OPENAI_API_KEY=%q\n" "$OPENAI_API_KEY"
    [ -n "${DYNAMO_SERVICE_API_URL:-}" ] && printf "export DYNAMO_SERVICE_API_URL=%q\n" "$DYNAMO_SERVICE_API_URL"
    [ -n "${DELETE_EML_AFTER_PROCESS:-}" ] && printf "export DELETE_EML_AFTER_PROCESS=%q\n" "$DELETE_EML_AFTER_PROCESS"
    [ -n "${ENABLE_EXTRACTION:-}" ] && printf "export ENABLE_EXTRACTION=%q\n" "$ENABLE_EXTRACTION"
    [ -n "${EXTRACTION_PROMPT_FILE:-}" ] && printf "export EXTRACTION_PROMPT_FILE=%q\n" "$EXTRACTION_PROMPT_FILE"
    [ -n "${MAX_BYTES:-}" ] && printf "export MAX_BYTES=%q\n" "$MAX_BYTES"
    [ -n "${DELETE_FILE_AFTER_PROCESS:-}" ] && printf "export DELETE_FILE_AFTER_PROCESS=%q\n" "$DELETE_FILE_AFTER_PROCESS"
    [ -n "${DEV_TEST_SCHEMA:-}" ] && printf "export DEV_TEST_SCHEMA=%q\n" "$DEV_TEST_SCHEMA"
    [ -n "${SHOP_DOMAIN:-}" ] && printf "export SHOP_DOMAIN=%q\n" "$SHOP_DOMAIN"
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
echo "Running S3 EML processing on startup..."
/app/run_s3_eml_processing.sh >> /var/log/cron.log 2>&1 || echo "Warning: Initial run failed, but continuing to start cron..."

# Start cron daemon
echo "Starting cron daemon..."
cron

# Tail cron log to keep container running and show output
echo "Tailing cron log..."
tail -f /var/log/cron.log

