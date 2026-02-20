#!/bin/bash
set -e

# Start BetterStack collector in background
echo "Starting BetterStack collector..."
curl -sSL https://raw.githubusercontent.com/BetterStackHQ/collector/main/install.sh | \
  COLLECTOR_SECRET="$COLLECTOR_SECRET" bash &

# Start the main application
echo "Starting FastAPI application..."
exec python run.py
