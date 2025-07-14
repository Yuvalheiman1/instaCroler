# 📸 Instacroler – Instagram Story Tracker Bot

A Python-based Telegram bot that scrapes Instagram stories every 5 minutes using [anonyig.com](https://anonyig.com), then sends them to a Telegram group. Built with Playwright and deployed on Railway.

---

## 🚀 Features
- 🕵️ Scrapes public Instagram stories via anonyig.com
- 📩 Sends updates directly to a Telegram group
- 🔁 Runs continuously (24/7) with automatic cleanup
- 🧹 Clears the `downloads/` folder every 10 hours
- 💾 Tracks monitored profiles and story history in JSON files

---

## 🧱 Project Structure

| File/Folder              | Purpose |
|--------------------------|---------|
| `run_bot_wrapper.py`     | Main entry point. Manages timed cleanup and restart logic. |
| `bot.py`                 | Telegram bot & scraping controller logic. |
| `anonyig_downloader.py`  | Logic for scraping Instagram stories using Anonyig |
| `stories_tracker.py`     | Tracks which stories have already been sent |
| `downloads/`             | Temporary files (cleared every 10 hours) |
| `monitored_profiles.json`| List of Instagram usernames being tracked |
| `stories_tracker.json`   | Cache of sent story IDs to avoid duplicates |
| `dlq.json`               | Failed download queue (optional retry mechanism) |
| `.env.example`           | Template for environment variables |
| `requirements.txt`       | Python dependencies |
| `railway_postinstall.sh` | Ensures Playwright is ready on Railway |

---

## 📦 Installation

### 1. Clone the repo
```bash
git clone https://github.com/YOUR_USERNAME/instacroler.git
cd instacroler
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set up environment variables
Copy `.env.example` to `.env` and fill in your Telegram bot token and chat ID.

### 4. Install Playwright browsers (required for scraping)
```bash
playwright install
```

---

## 🏃 Usage

### Local
Run the wrapper script to start the bot and enable periodic cleanup:
```bash
python run_bot_wrapper.py
```

### Railway
Deploy as a Python service. The `railway_postinstall.sh` script ensures Playwright is ready.

---

## ⚙️ Environment Variables

| Variable              | Description |
|-----------------------|-------------|
| `TELEGRAM_BOT_TOKEN`  | Telegram bot API token |
| `TELEGRAM_CHAT_ID`    | Target group/chat ID |

---

## 📝 Notes
- Only public Instagram stories are supported.
- The bot does not require Instagram login.
- All downloads are temporary and cleared every 10 hours.
- Failed downloads are logged in `dlq.json` for review.

---

## 🛠️ Contributing
Pull requests and issues are welcome!

---

## 📄 License
MIT
