FROM python:3.11-slim

# Install cron and AWS CLI
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    cron \
    awscli \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy Python requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY gmail.py .
COPY run_email_and_upload.sh .
RUN chmod +x run_email_and_upload.sh

# Copy crontab file
COPY crontab /etc/cron.d/email-collector-cron

# Give execution rights on the cron job
RUN chmod 0644 /etc/cron.d/email-collector-cron

# Apply cron job
RUN crontab /etc/cron.d/email-collector-cron

# Create log directory
RUN mkdir -p /app/logs

# Create data directory (optional, can be mounted)
RUN mkdir -p /app/data

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create cron log file
RUN touch /var/log/cron.log

# Health check - check if cron daemon is running
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD pgrep cron > /dev/null || exit 1

# Use entrypoint script
ENTRYPOINT ["/entrypoint.sh"]

