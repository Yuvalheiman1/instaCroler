#!/bin/bash

# This script determines which process to run based on the SERVICE_TYPE environment variable.
# This allows us to use the same Docker image for both the bot and the scraper services on Railway.

# Default to 'bot' if SERVICE_TYPE is not set
if [ -z "$SERVICE_TYPE" ]; then
  SERVICE_TYPE="bot"
fi

if [ "$SERVICE_TYPE" = "bot" ]; then
  # Run the main Telegram bot, which is a long-running process
  echo "INFO: Starting the Telegram Bot service (bot_main.py)..."
  exec python bot_main.py

elif [ "$SERVICE_TYPE" = "scraper" ]; then
  # Run the scraper script, which is a short-lived task for the cron job
  echo "INFO: Starting the Scraper job (run_scraper.py)..."
  exec python run_scraper.py

else
  # Fallback for safety, in case of a misconfiguration
  echo "ERROR: Unknown SERVICE_TYPE '$SERVICE_TYPE'. Please set it to 'bot' or 'scraper'."
  echo "Defaulting to bot service..."
  exec python bot_main.py
fi
