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
COPY . .

RUN pip install --no-cache-dir -r requirements.txt

# Copy all application files (excluding files in .dockerignore)

# Make scripts executable
RUN chmod +x run_s3_eml_processing.sh entrypoint.sh

# Crontab will be mounted as volume and applied at runtime via entrypoint

# Create log directory
RUN mkdir -p /app/logs

# Create data directory (optional, can be mounted)
RUN mkdir -p /app/data

# Move entrypoint script to root
RUN mv entrypoint.sh /entrypoint.sh

# Create cron log file
RUN touch /var/log/cron.log

# Health check - check if cron daemon is running
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD pgrep cron > /dev/null || exit 1

# Use entrypoint script
ENTRYPOINT ["/entrypoint.sh"]

