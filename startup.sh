#!/bin/bash
echo "Starting UNDP Reports Scraper..."

# Start Xvfb for headless Chrome
Xvfb :99 -ac -screen 0 1280x1024x16 &

# Start the application
exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --timeout 300 app:app