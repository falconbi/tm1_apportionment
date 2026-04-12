#!/bin/bash
# =============================================
# Stop CST ETL Poller
# =============================================

echo "[$(date)] Stopping CST ETL Poller..."

pkill -f "python3 etl/poller.py"

if [ $? -eq 0 ]; then
    echo "Poller stopped successfully."
else
    echo "No poller process was running."
fi
