# 📸 Instagram Story Monitor Bot

A robust Python-based Telegram bot that monitors Instagram stories and sends new content to your Telegram chat. Features automatic scraping, retry logic, pause/resume functionality, and comprehensive error handling.

---

## 🚀 Features

- 🕵️ **Anonymous Scraping**: Uses anonyig.com to scrape Instagram stories without authentication
- 📱 **Telegram Integration**: Full-featured bot with inline keyboards and commands
- ⏰ **Scheduled Monitoring**: Automatic checks every 5 minutes via Railway Cron
- � **Smart Retry Logic**: Exponential backoff for failed downloads and sends
- ⏸️ **Pause/Resume**: Control when the bot should run
- � **Status Monitoring**: Real-time status and statistics
- �️ **Redis Storage**: Fast, persistent storage with Redis database
- 🧹 **Error Handling**: Dead Letter Queue for failed operations
- � **Comprehensive Logging**: Detailed logs for debugging and monitoring

---

## 🏗️ Architecture

The bot is split into two main components:

### 1. **Main Bot** (`bot_main.py`)
- Handles Telegram user interaction
- Manages profile addition/removal
- Provides status and control commands
- Runs continuously to listen for commands

### 2. **Scheduled Scraper** (`run_scraper.py`)  
- Runs every 5 minutes via Railway Cron
- Checks for new stories from monitored profiles
- Downloads and sends new content
- Updates tracking data

---

## 🧱 Project Structure

| File/Folder              | Purpose |
|--------------------------|---------|
| `bot_main.py`            | Main Telegram bot for user interaction |
| `run_scraper.py`         | Scheduled scraper (runs via Railway Cron) |
| `setup_local.py`         | Quick setup script for local development |
| `migrate_to_redis.py`    | Migration script from JSON to Redis |
| `redis_health_check.py`  | Redis connection and health diagnostics |
| `src/downloader.py`      | Instagram story scraping logic |
| `src/database.py`        | Redis database management |
| `src/config.py`          | Configuration settings |
| `src/logger.py`          | Logging configuration |
| `dev_helper.py`          | Development and testing utilities |
| `data/`                  | Persistent data storage |
| `downloads/`             | Temporary story files |
| `logs/`                  | Application logs |
| `requirements.txt`       | Python dependencies |
| `Dockerfile`             | Docker configuration for Railway |
| `railway_postinstall.sh` | Railway deployment script |

---

## 📦 Installation

### Quick Setup (Recommended)
```bash
# Clone and setup in one go
git clone https://github.com/YOUR_USERNAME/instacroler.git
cd instacroler
python setup_local.py
```

### Manual Setup

### 1. Clone the repository
```bash
git clone https://github.com/YOUR_USERNAME/instacroler.git
cd instacroler
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set up environment variables
Copy `.env.example` to `.env` and configure:

**For Local Development:**
```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
REDIS_URL=redis://localhost:6379
LOG_LEVEL=INFO
```

**For Railway Deployment:**
```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
# REDIS_URL will be provided automatically by Railway
LOG_LEVEL=INFO
```

### 4. Set up Redis (for local development)

**Option 1: Install Redis locally**
```bash
# Windows (using Chocolatey)
choco install redis-64

# macOS (using Homebrew)
brew install redis

# Ubuntu/Debian
sudo apt install redis-server
```

**Option 2: Use Docker**
```bash
docker run -d --name redis -p 6379:6379 redis:alpine
```

### 5. Install Playwright browsers
```bash
playwright install chromium
```

### 6. Start Redis (local development only)
```bash
# If installed locally
redis-server

# If using Docker
docker start redis
```

### 7. Test Redis connection
```bash
python redis_health_check.py
```

### 8. Migrate existing data (if upgrading)
If you have existing JSON data files:
```bash
python migrate_to_redis.py
```

---

## 🏃 Usage

### Local Development
```bash
# 1. Start Redis first (if not using Docker)
redis-server

# 2. Run the main bot
python bot_main.py

# 3. Run the scraper manually (for testing)
python run_scraper.py
```

**Note**: For local development, you need Redis running. See the installation section above.

### Railway Deployment

1. **Deploy the main bot**: Set `bot_main.py` as the main service
2. **Set up Cron job**: Configure Railway Cron to run `python run_scraper.py` every 5 minutes
3. **Environment variables**: Set all required variables in Railway dashboard

### Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and bot introduction |
| `/help` | Show all available commands |
| `/status` | Display bot status and statistics |
| `/menu` | Show interactive button menu |
| `/add_profile <username>` | Add Instagram profile to monitor |
| `/remove_profile <username>` | Remove profile from monitoring |
| `/list_profiles` | Show all monitored profiles |
| `/refresh` | Manually trigger story check |
| `/pause` | Pause automatic scraping |
| `/resume` | Resume automatic scraping |

---

## 🔧 Configuration

### Storage Options

**JSON Storage** (default):
- Uses local JSON files in `data/` directory
- Perfect for small deployments
- No additional setup required

**PostgreSQL Storage** (optional):
- Set `DATABASE_URL` environment variable
- Suitable for production deployments
- Better for multiple instances

### Customization

Edit `src/config.py` to customize:
- Scraping timeouts and delays
- File extensions and paths
- Rate limiting settings
- Logging configuration

---

## 🚀 Railway Deployment

### 1. Fork and Deploy
- Fork this repository
- Connect to Railway
- Deploy from your fork

### 2. Set Environment Variables
```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
REDIS_URL=redis://redis:6379
LOG_LEVEL=INFO
```

### 3. Add Redis Service
In Railway dashboard:
- Add a Redis service to your project
- Railway will automatically provide the `REDIS_URL` environment variable

### 3. Configure Cron Job
In Railway dashboard:
- Go to your service settings  
- Add a Cron job with schedule: `*/5 * * * *` (every 5 minutes)
- Command: `python run_scraper.py`

---

## 🔧 Configuration

### Redis Database

The bot uses Redis for persistent storage, providing:
- **Fast Performance**: In-memory data structure store
- **Persistence**: Data survives application restarts
- **Scalability**: Easy to scale and manage
- **Railway Integration**: Automatically configured when Redis service is added

### Storage Structure

```json
{
  "monitored_profiles": {
    "chat_id": {
      "username": {
        "last_story_id": "story_123",
        "added_at": "2025-07-20T10:30:00",
        "last_check": "2025-07-20T10:35:00",
        "fail_count": 0
      }
    }
  },
  "bot_paused": "1",
  "dlq": [...]
}
```

### Customization

Edit `src/config.py` to customize:
- Scraping timeouts and delays
- File extensions and paths
- Rate limiting settings
- Logging configuration

---

## 🛠️ Troubleshooting

### Common Issues

**Bot not responding to commands:**
- Check `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`
- Verify bot has permission to send messages
- Check Railway logs for errors

**Stories not downloading:**
- Check if anonyig.com is accessible
- Verify Playwright browser installation
- Check profile names are correct (no @ symbol)

**Redis connection errors:**
- **Local Development**: 
  - Install Redis locally or use Docker
  - Start Redis server: `redis-server` or `docker start redis`
  - Set `REDIS_URL=redis://localhost:6379` in your `.env` file
- **Railway Deployment**:
  - Verify `REDIS_URL` environment variable is set
  - Check that Redis service is running on Railway
  - Ensure Redis service is in the same Railway project

**"REDIS_URL not set" error:**
- For local: Add `REDIS_URL=redis://localhost:6379` to your `.env` file
- For Railway: Add Redis service in Railway dashboard (auto-configures)

**Data persistence issues:**
- Check Redis connection in Railway logs
- Verify Redis service has sufficient memory
- Monitor Redis key expiration policies

**Migration from JSON to Redis:**
- Run `python migrate_to_redis.py` to migrate existing data
- Use `python redis_health_check.py` to verify Redis connectivity
- Original JSON files are backed up automatically during migration

**Frequent failures:**
- Profiles with too many failures (3+) are temporarily skipped
- Use `/status` to see profile health
- Check logs for specific error messages

### Debug Mode
Set `LOG_LEVEL=DEBUG` for detailed logging.

---

## 📝 License

This project is for educational purposes. Respect Instagram's terms of service and rate limits.

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

---

## ⚠️ Disclaimer

This tool is for educational and personal use only. Users are responsible for complying with Instagram's terms of service and applicable laws.
Deploy as a Python service. The `railway_postinstall.sh` script ensures Playwright is ready.

---

## ⚙️ Environment Variables

| Variable              | Description |
|-----------------------|-------------|
| `TELEGRAM_BOT_TOKEN`  | Telegram bot API token |
| `TELEGRAM_CHAT_ID`    | Target group/chat ID |
| `REDIS_URL`          | Redis database connection URL (provided by Railway) |
| `LOG_LEVEL`          | Logging level (DEBUG, INFO, WARNING, ERROR) |

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
