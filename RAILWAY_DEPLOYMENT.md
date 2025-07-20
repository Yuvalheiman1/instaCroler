# Railway Deployment Guide for InstaCroler

This guide will walk you through deploying the InstaCroler bot and scraper to Railway using a two-service architecture from a single repository.

## Overview

To run both a 24/7 Telegram bot and a scheduled scraper, we will deploy two separate services on Railway from the same GitHub repository.

1.  **Bot Service**: This service will run continuously to handle user interactions with the Telegram bot.
2.  **Scraper Service**: This service will be triggered by a cron schedule to run the scraper script, download new stories, and send them to you.

This is managed by a `start.sh` script and a `SERVICE_TYPE` environment variable that tells each service which process to run.

## Prerequisites

1.  **GitHub Repository**: Your project code should be in a GitHub repository.
2.  **Railway Account**: You need a Railway account.
3.  **Telegram Bot Token**: Have your Telegram Bot Token ready.
4.  **Telegram Chat ID**: Know the chat ID where the bot will send stories.

## Deployment Steps

### Step 1: Deploy the Bot Service

1.  Log in to your Railway account and go to your dashboard.
2.  Click **New Project** and select **Deploy from GitHub repo**.
3.  Choose your `instaCroler` repository. Railway will automatically detect the `Dockerfile` and start building.
4.  Once the deployment is active, go to the service's **Settings** tab.
    *   **Service Name**: Rename the service to something descriptive, like `instacroler-bot`.
5.  Go to the **Variables** tab and add the following environment variables:
    *   `SERVICE_TYPE`: Set this to `bot`. This is crucial for telling the service to run the bot.
    *   `TELEGRAM_BOT_TOKEN`: Your secret token from BotFather.
    *   `TELEGRAM_CHAT_ID`: The chat ID for the bot to send messages to.
    *   `PYTHONUNBUFFERED`: Set this to `1`.

This service will now run `bot_main.py` and your Telegram bot will be online.

### Step 2: Deploy the Scraper Service

Now, we will deploy the *same repository* again as a new service for the scraper.

1.  Go back to your Railway project dashboard.
2.  Click **New** and again select **Deploy from GitHub repo**.
3.  Select the **exact same `instaCroler` repository**. Railway will create a new, separate service.
4.  Once the deployment is active, go to this new service's **Settings** tab.
    *   **Service Name**: Rename it to something like `instacroler-scraper`.
    *   **Cron Schedule**: This is the most important part for this service. Set your desired schedule. For example, to run the scraper every 5 minutes, use: `*/5 * * * *`.
5.  Go to the **Variables** tab and add the same set of variables, but with one key difference:
    *   `SERVICE_TYPE`: Set this to `scraper`. This tells the service to run the scraper script when triggered by the cron schedule.
    *   `TELEGRAM_BOT_TOKEN`: The same token as the bot service.
    *   `TELEGRAM_CHAT_ID`: The same chat ID as the bot service.
    *   `PYTHONUNBUFFERED`: Set this to `1`.

### Step 3: Provision a Redis Database (Crucial for Data Saving)

To ensure that your list of monitored profiles, the pause flag, and other data persists across restarts and is shared between both services, you must provision a Redis database.

1.  In your Railway project dashboard, click the **New** button and select **Database**.
2.  Choose **Redis** from the list of available databases.
3.  Railway will create a new Redis service within your project.
4.  **Crucially, Railway will automatically inject the connection string as a `REDIS_URL` environment variable into both your `instacroler-bot` and `instacroler-scraper` services.**

That's it! The application code is already configured to detect and use this `REDIS_URL` variable to connect to the database. No further steps are needed to link the services.

## How It Works

-   When the **bot service** starts, the `start.sh` script sees `SERVICE_TYPE=bot` and executes `python bot_main.py`. It runs continuously.
-   When the **scraper service** is triggered by its cron schedule, the `start.sh` script sees `SERVICE_TYPE=scraper` and executes `python run_scraper.py`. It runs, scrapes, sends stories, and then shuts down until the next scheduled run.

## Managing Your Bot

-   **Adding/Removing Profiles**: Interact with your bot on Telegram (`/add_profile`, `/remove_profile`). The changes are saved in the shared Redis database.
-   **Pausing/Resuming**: Use `/pause` and `/resume`. This sets a flag in the Redis database. The scraper service checks for this flag at the start of each run and will skip scraping if it exists.

You now have a fully functional and correctly deployed bot and scraper!
