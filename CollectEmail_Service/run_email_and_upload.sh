#!/usr/bin/env bash
set -euo pipefail

# Load environment variables if cron-env file exists (for cron jobs)
if [ -f /app/cron-env ]; then
    set -a
    source /app/cron-env
    set +a
fi

# Docker environment paths
SCRIPT_DIR="/app"
PYTHON="/usr/local/bin/python3"
SCRIPT="$SCRIPT_DIR/gmail.py"
OUTPUT_DIR="${OUTPUT_DIR:-/app/data}"
LOG_DIR="/app/logs"

# S3 configuration from environment variables
BUCKET="${S3_BUCKET:-pipe-and-ro-email}"
S3_PREFIX="${S3_PREFIX:-exports}"
AWS_REGION="${AWS_REGION:-ap-southeast-1}"

# Set AWS region
export AWS_REGION="$AWS_REGION"

# Ensure directories exist
mkdir -p "$LOG_DIR"
mkdir -p "$OUTPUT_DIR"

TS="$(date +'%Y%m%d_%H%M%S')"
LOG_FILE="$LOG_DIR/cron_${TS}.log"

{
  echo "=== Run started: $(date) ==="
  echo "Python: $PYTHON"
  echo "Script: $SCRIPT"
  echo "Output directory: $OUTPUT_DIR"
  echo "Bucket: s3://$BUCKET/$S3_PREFIX/"
  echo "AWS Region: $AWS_REGION"

  # 1) Run email collection Python script
  if ! "$PYTHON" "$SCRIPT" --output-dir "$OUTPUT_DIR"; then
    echo "ERROR: Python script failed with exit code $?"
    exit 1
  fi

  # 2) Upload results to S3
  # Sync emails.json (overwrites existing)
  if [ -f "$OUTPUT_DIR/emails.json" ]; then
    aws s3 cp "$OUTPUT_DIR/emails.json" "s3://$BUCKET/$S3_PREFIX/emails.json" --only-show-errors
    echo "Synced emails.json to S3"
  else
    echo "WARNING: emails.json not found"
  fi

  # Sync raw_emails directory (incremental)
  if [ -d "$OUTPUT_DIR/raw_emails" ]; then
    aws s3 sync "$OUTPUT_DIR/raw_emails/" "s3://$BUCKET/$S3_PREFIX/raw_emails/" --only-show-errors
    echo "Synced raw_emails/ to S3"
  else
    echo "WARNING: raw_emails/ directory not found"
  fi

  # Note: Attachments remain local only (not synced to S3 per plan)

  echo "=== Run finished: $(date) ==="
} >> "$LOG_FILE" 2>&1

