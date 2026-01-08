#!/usr/bin/env bash
set -euo pipefail

# Load environment variables if cron-env file exists (for cron jobs)
if [ -f /app/cron-env ]; then
    set -a
    source /app/cron-env
    set +a
fi

# Set working directory to /app to ensure relative paths work correctly
cd /app || exit 1

# Docker environment paths
SCRIPT_DIR="/app"
PYTHON="/usr/local/bin/python3"
SCRIPT="$SCRIPT_DIR/orchestrate_s3_eml.py"
OUTPUT_DIR="${OUTPUT_DIR:-/app/data}"
LOG_DIR="/app/logs"

# S3 configuration from environment variables
BUCKET="${S3_BUCKET:-pipe-and-ro-email}"
S3_PREFIX="${S3_PREFIX:-exports/raw_emails}"
AWS_REGION="${AWS_REGION:-ap-southeast-1}"

# Set AWS region and output directory
export AWS_REGION="$AWS_REGION"
export OUTPUT_DIR="$OUTPUT_DIR"
export S3_BUCKET="$BUCKET"
export S3_PREFIX="$S3_PREFIX"

# Ensure directories exist
mkdir -p "$LOG_DIR"
mkdir -p "$OUTPUT_DIR"

TS="$(date +'%Y%m%d_%H%M%S')"
LOG_FILE="$LOG_DIR/s3_eml_processing_${TS}.log"

{
  echo "=== Run started: $(date) ==="
  echo "Python: $PYTHON"
  echo "Script: $SCRIPT"
  echo "Output directory: $OUTPUT_DIR"
  echo "Bucket: s3://$BUCKET/$S3_PREFIX/"
  echo "AWS Region: $AWS_REGION"

  # Run S3 EML processing script
  if ! "$PYTHON" "$SCRIPT"; then
    echo "ERROR: S3 EML processing script failed with exit code $?"
    exit 1
  fi

  echo "=== Run finished: $(date) ==="
} >> "$LOG_FILE" 2>&1

