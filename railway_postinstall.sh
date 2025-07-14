#!/bin/bash

# Install system dependencies (if needed)
# Railway provides a base Python image so usually no need here

# Ensure Playwright's Chromium browser is installed
playwright install chromium



# Print Python version for debug
python --version

echo "✅ Postinstall complete. Environment ready!"
