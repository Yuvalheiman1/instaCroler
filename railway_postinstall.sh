#!/bin/bash
set -e # Exit immediately if a command exits with a non-zero status.

echo "🚀 Starting railway_postinstall.sh script..."

# Create required directories
echo "📁 Creating required directories..."
mkdir -p data downloads

# Ensure Playwright's Chromium browser and its system dependencies are installed
# The --with-deps flag is crucial for server environments
echo "📦 Installing Playwright Chromium browser with dependencies..."
playwright install chromium --with-deps

# Set up daily cleanup cron job
echo "⏰ Setting up daily cleanup job..."
echo "0 0 * * * /usr/local/bin/python /app/cleanup.py >> /app/cleanup.log 2>&1" > /etc/cron.d/cleanup-cron
chmod 0644 /etc/cron.d/cleanup-cron
crontab /etc/cron.d/cleanup-cron

# Print Python version for debug (good to keep)
echo "🐍 Python version:"
python --version

echo "✅ Postinstall complete. Environment ready!"