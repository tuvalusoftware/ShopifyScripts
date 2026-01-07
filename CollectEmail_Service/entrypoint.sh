#!/bin/bash
set -e

echo "Starting email collector container..."

# Run immediately on container start
echo "Running email collection on startup..."
/app/run_email_and_upload.sh >> /var/log/cron.log 2>&1

# Start cron daemon
echo "Starting cron daemon..."
cron

# Tail cron log to keep container running and show output
echo "Tailing cron log..."
tail -f /var/log/cron.log

