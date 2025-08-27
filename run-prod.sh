#!/bin/bash
echo "Starting in PRODUCTION mode..."
export ENVIRONMENT=production
export PORT=8000

# Start Xvfb for headless Chrome
if ! pgrep -x "Xvfb" > /dev/null; then
    Xvfb :99 -ac -screen 0 1280x1024x16 &
    export DISPLAY=:99
fi

# Use gunicorn for production
gunicorn --config gunicorn.conf.py app:app