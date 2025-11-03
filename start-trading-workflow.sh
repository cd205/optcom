#!/bin/bash

# Trading Workflow Auto-Startup Script
# This script starts the trading workflow automatically on VM boot

set -e  # Exit on any error

# Add miniconda to PATH for Python and Airflow
export PATH="/home/chris_s_dodd/miniconda3/bin:$PATH"

LOG_FILE="/home/chris_s_dodd/optcom-1/trading-workflow-startup.log"

# Function to log messages
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

log_message "Starting trading workflow initialization..."

# Change to the airflow project directory
cd /home/chris_s_dodd/optcom-1/airflow_project || {
    log_message "ERROR: Failed to change to airflow_project directory"
    exit 1
}

log_message "Changed to directory: $(pwd)"

# Aggressive cleanup of all trading-related processes
log_message "Performing aggressive cleanup of all trading-related processes..."

# Function to kill processes by pattern with retry
kill_processes_with_retry() {
    local pattern="$1"
    local description="$2"
    local max_attempts=3

    for attempt in $(seq 1 $max_attempts); do
        log_message "Attempt $attempt: Looking for $description processes..."
        pids=$(pgrep -f "$pattern" 2>/dev/null || true)

        if [ -z "$pids" ]; then
            log_message "✅ No $description processes found"
            return 0
        fi

        log_message "🛑 Killing $description processes: $pids"
        pkill -f "$pattern" 2>/dev/null || true
        sleep 3

        # Check if any survived and force kill
        remaining=$(pgrep -f "$pattern" 2>/dev/null || true)
        if [ -n "$remaining" ]; then
            log_message "⚡ Force killing remaining $description processes: $remaining"
            pkill -9 -f "$pattern" 2>/dev/null || true
            sleep 2
        fi

        # Final check
        final_check=$(pgrep -f "$pattern" 2>/dev/null || true)
        if [ -z "$final_check" ]; then
            log_message "✅ All $description processes terminated"
            return 0
        fi
    done

    log_message "⚠️ Warning: Some $description processes may still be running"
}

# Clean up all trading system processes
kill_processes_with_retry "airflow" "Airflow"
kill_processes_with_retry "java.*IbcGateway" "IB Gateway"
kill_processes_with_retry "price_monitor" "Price Monitor"
kill_processes_with_retry "trading_monitor" "Trading Monitor"
kill_processes_with_retry "vertical_spread" "Order Placement"

# Try make stop for good measure
log_message "Running make stop for additional cleanup..."
make stop 2>&1 | tee -a "$LOG_FILE" || log_message "Warning: make stop failed or no processes to stop"

# Clean up stale files
log_message "Cleaning up stale files..."
find /home/chris_s_dodd/optcom-1 -name "*.pid" -type f -delete 2>/dev/null || true
find /tmp -name "*optcom*" -type f -delete 2>/dev/null || true
find /tmp -name "*airflow*" -type f -delete 2>/dev/null || true

# Wait for cleanup to complete
log_message "Waiting for cleanup to complete..."
sleep 10

# Set AIRFLOW_HOME environment variable
export AIRFLOW_HOME="/home/chris_s_dodd/optcom-1/airflow_project"
log_message "Set AIRFLOW_HOME to: $AIRFLOW_HOME"

# Start airflow in standalone mode
log_message "Starting Airflow standalone..."
nohup airflow standalone > airflow.log 2>&1 &
AIRFLOW_PID=$!
log_message "Started Airflow with PID: $AIRFLOW_PID"

# Wait for Airflow to initialize
log_message "Waiting for Airflow to initialize..."
sleep 15

# Check if Airflow is still running
if ! kill -0 $AIRFLOW_PID 2>/dev/null; then
    log_message "ERROR: Airflow process died during startup"
    log_message "Last few lines from airflow.log:"
    tail -10 airflow.log >> "$LOG_FILE" 2>&1 || log_message "Could not read airflow.log"
    exit 1
fi

# Wait a bit more and check if Airflow webserver is responding
log_message "Checking if Airflow webserver is responding..."
for i in {1..6}; do
    if curl -s -f http://localhost:8080/health > /dev/null 2>&1; then
        log_message "Airflow webserver is responding"
        break
    else
        log_message "Attempt $i: Airflow webserver not yet ready, waiting..."
        sleep 10
    fi
    
    if [ $i -eq 6 ]; then
        log_message "WARNING: Airflow webserver not responding after 60 seconds, proceeding anyway..."
    fi
done

# Start the trading workflow
log_message "Starting trading workflow with make start..."
make start 2>&1 | tee -a "$LOG_FILE" || {
    log_message "ERROR: Failed to start trading workflow"
    exit 1
}

# Health check - verify components are running
log_message "Performing post-startup health check..."

# Check if Airflow is still running
if ! kill -0 $AIRFLOW_PID 2>/dev/null; then
    log_message "❌ ERROR: Airflow process died after workflow start"
    exit 1
fi

# Wait for workflow to initialize
log_message "Waiting for workflow to initialize..."
sleep 30

# Check workflow status
log_message "Checking workflow status..."
cd /home/chris_s_dodd/optcom-1/airflow_project
make status 2>&1 | tee -a "$LOG_FILE" || log_message "Warning: Could not check workflow status"

log_message "🎉 Trading workflow startup completed successfully!"
log_message "Airflow PID: $AIRFLOW_PID"
log_message "Check airflow.log for Airflow-specific logs"
log_message "Check trading-workflow-startup.log for startup logs"
log_message "Use 'make status' to monitor workflow progress"