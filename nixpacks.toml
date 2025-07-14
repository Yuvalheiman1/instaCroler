FROM python:3.10-slim

# Install system dependencies required by Playwright
RUN apt-get update && apt-get install -y \
  curl wget libasound2 libicu-dev libffi-dev libx264-164 \
  libgbm-dev libnss3 libnspr4 libatk-bridge2.0-0 libxkbcommon0 \
  libdrm-dev libatspi2.0-0 libxcomposite1 libxdamage1 libxfixes3 \
  libxrandr2 libpangocairo-1.0-0 libgtk-3-0 \
  && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install in venv
COPY requirements.txt .

# Create virtualenv
RUN python -m venv /opt/venv

# Install Python packages first (this includes Playwright itself!)
RUN /opt/venv/bin/pip install --upgrade pip && /opt/venv/bin/pip install -r requirements.txt

# ✅ Now we can install Playwright’s browser — after it's installed as a Python package
RUN /opt/venv/bin/python -m playwright install chromium

# Copy the rest of your app
COPY . .

# Start your app
CMD ["/opt/venv/bin/python", "run_bot_wrapper.py"]
