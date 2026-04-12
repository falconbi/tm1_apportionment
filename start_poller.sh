#!/bin/bash
# =============================================
# CST ETL Poller Startup Script
# =============================================

cd ~/apps/tm1_apportionment

echo "[$(date)] Starting CST ETL Poller..."

# Kill any existing poller instance to avoid duplicates
pkill -f "python3 etl/poller.py" 2>/dev/null

# Start the poller with 15 second interval
nohup python3 etl/poller.py --interval 15 > poller.log 2>&1 &

echo "[$(date)] Poller started successfully (PID $!)"
echo "   Interval : 15 seconds"
echo "   Log file : poller.log"
echo ""
echo "To stop the poller:   pkill -f 'python3 etl/poller.py'"
echo "To check status:      ps aux | grep poller.py"
