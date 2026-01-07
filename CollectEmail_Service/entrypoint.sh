#!/bin/bash
set -e

echo "Starting email collector container..."

# Start cron daemon
echo "Starting cron daemon..."
cron

# Tail cron log to keep container running and show output
echo "Tailing cron log..."
tail -f /var/log/cron.log

