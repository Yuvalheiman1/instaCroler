#!/bin/bash
set -e # Exit immediately if a command exits with a non-zero status.

echo "🚀 Starting railway_postinstall.sh script..."

# Ensure Playwright's Chromium browser and its system dependencies are installed
# The --with-deps flag is crucial for server environments
echo "📦 Installing Playwright Chromium browser with dependencies..."

# Print Python version for debug (good to keep)
echo "🐍 Python version:"
python --version

echo "✅ Postinstall complete. Environment ready!"