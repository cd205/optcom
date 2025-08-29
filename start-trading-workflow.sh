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

# Stop any existing airflow processes
log_message "Stopping existing airflow processes..."
make stop 2>&1 | tee -a "$LOG_FILE" || log_message "Warning: make stop failed or no processes to stop"

# Kill any remaining airflow processes
log_message "Killing any remaining airflow processes..."
pkill -f airflow || log_message "Warning: no airflow processes found to kill"

# Wait for processes to fully terminate
log_message "Waiting for processes to terminate..."
sleep 5

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

log_message "Trading workflow startup completed successfully!"
log_message "Airflow PID: $AIRFLOW_PID"
log_message "Check airflow.log for Airflow-specific logs"