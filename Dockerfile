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

# Copy requirements first for better caching
COPY requirements.txt .
RUN python -m venv /opt/venv
RUN . /opt/venv/bin/activate && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create necessary directories and set permissions
RUN mkdir -p downloads data && \
    chmod 777 downloads data

# Set permissions
RUN chmod +x railway_postinstall.sh

# Install Playwright browser
RUN /opt/venv/bin/python -m playwright install chromium

# Add virtual environment to PATH
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/app:$PYTHONPATH"

# Default start command
CMD ["python", "run_bot_wrapper.py"]
