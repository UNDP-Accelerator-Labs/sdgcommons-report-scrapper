FROM python:3.11-slim 

# Install system dependencies (curated list to avoid unavailable packages)
RUN apt-get update && apt-get install -y \
    wget \
    gnupg2 \
    ca-certificates \
    unzip \
    curl \
    xvfb \
    fonts-liberation \
    libappindicator3-1 \
    libglib2.0-0 \
    libnss3 \
    libxss1 \
    libxtst6 \
    libgtk-3-0 \
    libx11-xcb1 \
    libxcb-dri3-0 \
    libdrm2 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libasound2 \
    libpangocairo-1.0-0 \
    libatk1.0-0 \
    libcairo2 \
    libgdk-pixbuf-xlib-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Chromium (multi-arch friendly) and required libs
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    wget \
    gnupg2 \
    ca-certificates \
    unzip \
    curl \
    xvfb \
    fonts-liberation \
    libappindicator3-1 \
    libglib2.0-0 \
    libnss3 \
    libxss1 \
    libxtst6 \
    libgtk-3-0 \
    libx11-xcb1 \
    libxcb-dri3-0 \
    libdrm2 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libasound2 \
    libpangocairo-1.0-0 \
    libatk1.0-0 \
    libcairo2 \
    libgdk-pixbuf-xlib-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Point Selenium to the Chromium binary
ENV CHROME_BIN=/usr/bin/chromium

# Ensure app port is set and a writable temp dir exists (created at build time)
ENV PORT=8000
RUN mkdir -p /temp && chmod 1777 /temp

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99
ENV ENVIRONMENT=production

# Set work directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# Expose port (matches PORT env)
EXPOSE ${PORT}

# Health check uses the PORT env
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Start the application with gunicorn
CMD ["sh", "-c", "Xvfb :99 -ac -screen 0 1280x1024x16 & exec gunicorn --config gunicorn.conf.py app:app"]