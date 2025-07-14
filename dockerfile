# Use a lightweight Python base image
FROM python:3.10-slim

# Install OS-level dependencies for Playwright
RUN apt-get update && apt-get install -y \
    curl wget libasound2 libicu-dev libffi-dev libx264-164 \
    libgbm-dev libnss3 libnspr4 libatk-bridge2.0-0 libxkbcommon0 \
    libdrm-dev libatspi2.0-0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libpangocairo-1.0-0 libgtk-3-0 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Create virtual environment
RUN python -m venv /opt/venv

# Install Python dependencies in venv
RUN /opt/venv/bin/pip install --upgrade pip && /opt/venv/bin/pip install -r requirements.txt

# Install Playwright browser
RUN /opt/venv/bin/python -m playwright install chromium

# Default start command
CMD ["/opt/venv/bin/python", "run_bot_wrapper.py"]
