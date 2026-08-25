# 📸 Instagram Story Monitor Bot

A Telegram bot that watches public Instagram profiles and forwards new stories to a
Telegram chat. Stories are scraped anonymously from anonyig.com with Playwright, and
all state is kept in Redis.

---

## 🚀 Features

- 🕵️ **Anonymous scraping**: uses anonyig.com, so no Instagram login is needed
- 📱 **Telegram control**: add and remove profiles, check status, pause and resume from chat
- ⏰ **Scheduled checks**: `run_scraper.py` is a one-shot job meant to be run on a cron schedule
- 🔁 **Download retries**: up to 3 attempts per file with a linear backoff between them
- 📤 **Threaded delivery**: downloaded files go through an in-process queue drained by two daemon worker threads
- 💀 **Dead letter queue**: sends that fail are stored in Redis (last 100) so they are not lost silently
- 🗄️ **Redis storage**: monitored profiles, last seen story IDs and the pause flag survive restarts
- 📝 **File logging**: per-run log files under `logs/`

---

## 🏗️ How it works

### 1. Main bot (`bot_main.py`)

A long-running process that talks to Telegram. It handles the commands, keeps the list of
monitored profiles in Redis, and can pause or resume the scraper.

### 2. Scraper job (`run_scraper.py`)

A short-lived job, meant to be triggered on a schedule. It reads the monitored profiles
from Redis and works through them **one at a time**: a profile is scraped, its new stories
are downloaded and queued for Telegram, and only then does the next profile start. There is
no parallelism across profiles - one browser session at a time keeps anonyig.com from
rejecting the traffic.

Optional flags:

```bash
python run_scraper.py --profile some_username   # only that profile
python run_scraper.py --chat 123456789          # only that chat's profiles
```

### 3. Delivery queue (`src/downloader.py`)

Sending to Telegram is where the concurrency actually is. `TelegramSender` keeps a
`queue.Queue` that is drained by two daemon threads (`max_concurrent_workers` in
`src/config.py`). Each worker uploads a file to the Telegram API; a file that still fails
after its download retries is pushed to the Redis dead letter queue under the `dlq` key,
capped at the last 100 entries. `redis_health_check.py` prints how many entries are waiting
there.

---

## 🧱 Project structure

| File/Folder              | Purpose |
|--------------------------|---------|
| `bot_main.py`            | Telegram bot for user interaction |
| `run_scraper.py`         | One-shot scraper job, run on a schedule |
| `redis_health_check.py`  | Redis connection check and DLQ/profile diagnostics |
| `recored.py`             | Manual Playwright walk-through of the anonyig.com flow, for debugging selectors |
| `dev_helper.py`          | Placeholder for development utilities |
| `src/downloader.py`      | Scraping, downloading and the threaded Telegram delivery queue |
| `src/database.py`        | Redis access: profiles, pause flag, dead letter queue |
| `src/config.py`          | Selectors, timeouts, retry and worker settings |
| `src/logger.py`          | Logging configuration |
| `docker-compose.yml`     | Local Redis service |
| `Dockerfile`             | Image used for deployment |
| `start.sh`               | Entry point, picks bot or scraper from `SERVICE_TYPE` |
| `railway_postinstall.sh` | Installs the Playwright browser on the host |
| `requirements.txt`       | Python dependencies |
| `downloads/`, `logs/`    | Created at runtime, both git-ignored |

---

## 💻 Local setup

Requires Python 3.10+ and Docker (for Redis).

```bash
git clone https://github.com/Yuvalheiman1/instaCroler.git
cd instaCroler

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium

docker compose up -d redis        # Redis on localhost:6379

cp .env.example .env              # fill in your bot token and chat ID
```

Then run either half:

```bash
python bot_main.py                # the Telegram bot
python run_scraper.py             # one scrape pass
python redis_health_check.py      # check Redis, profiles and the DLQ
```

---

## ⚙️ Environment variables

| Variable             | Required | Description |
|----------------------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | yes      | Telegram bot API token |
| `TELEGRAM_CHAT_ID`   | yes      | Default chat the stories are sent to |
| `REDIS_URL`          | yes      | Redis connection URL, e.g. `redis://localhost:6379` |
| `LOG_LEVEL`          | no       | `DEBUG`, `INFO`, `WARNING` or `ERROR`. Defaults to `INFO` |
| `SERVICE_TYPE`       | no       | Read by `start.sh` in Docker: `bot` (default) or `scraper` |

---

## 🤖 Bot commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and bot introduction |
| `/help` | Show all available commands |
| `/status` | Display bot status and statistics |
| `/menu` | Show interactive button menu |
| `/add_profile <username>` | Add an Instagram profile to monitor |
| `/remove_profile <username>` | Remove a profile from monitoring |
| `/list_profiles` | Show all monitored profiles |
| `/refresh` | Manually trigger a story check |
| `/pause` | Pause automatic scraping |
| `/resume` | Resume automatic scraping |

---

## 🚢 Deployment

The image built from the `Dockerfile` runs `start.sh`, which picks a role from
`SERVICE_TYPE`. The intended setup is two services on the same image:

1. **Bot service**: `SERVICE_TYPE=bot`, a long-running process
2. **Scraper job**: `SERVICE_TYPE=scraper`, triggered by a cron schedule such as
   `*/5 * * * *`

Both need `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` and `REDIS_URL`. On Railway, adding a
Redis service provides `REDIS_URL` automatically.

---

## 🗄️ Redis keys

| Key | Contents |
|-----|----------|
| `monitored_profiles` | Per chat ID, per username: `last_story_id`, `added_at`, `last_check`, `fail_count` |
| `bot_paused` | `"1"` while the scraper is paused |
| `dlq` | Last 100 failed Telegram sends |

---

## 🛠️ Troubleshooting

**Bot not responding to commands**
- Check `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`
- Check the logs in `logs/`

**Stories not downloading**
- Check that anonyig.com is reachable and that its page layout still matches the selectors
  in `src/config.py`; `recored.py` walks the flow in a visible browser so you can see where
  it breaks
- Verify the Playwright browser is installed: `python -m playwright install chromium`
- Profile names must be given without the `@`

**Redis connection errors**
- Local: start Redis (`docker compose up -d redis`) and set
  `REDIS_URL=redis://localhost:6379` in `.env`
- Deployed: make sure the Redis service is running and `REDIS_URL` is set
- `python redis_health_check.py` reports exactly what it can and cannot reach

Set `LOG_LEVEL=DEBUG` for verbose logging.

---

## 📝 Notes and limits

- Only public Instagram stories are supported, and only what anonyig.com exposes
- Scraping depends on anonyig.com's markup, so selectors in `src/config.py` need updating
  when that site changes
- Downloaded files are written to `downloads/` and are not cleaned up automatically
- There are no automated tests in this repository yet

---

## ⚠️ Disclaimer

This tool is for educational and personal use only. Users are responsible for complying
with Instagram's terms of service and applicable laws.

---

## 📄 License

MIT
