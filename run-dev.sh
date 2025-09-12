#!/bin/bash
echo "Starting in DEVELOPMENT mode..."
export ENVIRONMENT=development
export PORT=8080
export FLASK_APP=app.py
# Use Flask built-in reloader so code changes are picked up automatically during development
python -m flask run --reload --host=0.0.0.0 --port=${PORT}

# TO RUN:
# # make the script executable (only needed once)
# chmod +x run-dev.sh

# # run the dev script
# ./run-dev.sh