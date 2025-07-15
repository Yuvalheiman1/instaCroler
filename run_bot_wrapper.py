import os
import shutil
import time
import subprocess

DOWNLOADS_DIR = os.path.join(os.path.dirname(__file__), 'downloads')
BOT_SCRIPT = os.path.join(os.path.dirname(__file__), 'bot.py')
PYTHON_EXEC = 'python'  # or 'python3' if needed
INTERVAL_SECONDS = 2 * 60 * 60  # 10 hours

def delete_downloads():
    if os.path.exists(DOWNLOADS_DIR):
        shutil.rmtree(DOWNLOADS_DIR)
        print(f"Deleted {DOWNLOADS_DIR}")
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)

def run_bot():
    print("Starting bot.py...")
    return subprocess.Popen([PYTHON_EXEC, BOT_SCRIPT])

def main():
    delete_downloads()
    print("Cleaning downloads and starting bot...")
    bot_proc = run_bot()
    try:
        while True:
            time.sleep(INTERVAL_SECONDS)
            print("Cleaning downloads and restarting bot...")
            delete_downloads()
            bot_proc.terminate()
            bot_proc.wait()
            bot_proc = run_bot()
    except KeyboardInterrupt:
        print("Exiting wrapper...")
        bot_proc.terminate()
        bot_proc.wait()

if __name__ == "__main__":
    main()
