#!/bin/bash

# IB Gateway Startup Script
# Following IBC best practices for automated trading systems

# =============================================================================
# Configuration Variables
# =============================================================================

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IBC_PATH="${SCRIPT_DIR}/ibc"
TWS_PATH="${SCRIPT_DIR}/tws"
CONFIG_PATH="${SCRIPT_DIR}/config"
LOG_DIR="${SCRIPT_DIR}/logs"

# IBC Settings
IBC_JAR="${IBC_PATH}/IBC.jar"
CONFIG_FILE="${CONFIG_PATH}/config.ini"
TWS_SETTINGS_PATH="${TWS_PATH}"

# Gateway specific settings
GATEWAY_OR_TWS="gateway"  # Use "gateway" for IB Gateway, "tws" for TWS
JAVA_CP="${IBC_JAR}:${TWS_PATH}/jars/*"
TRADING_MODE="paper"  # Change to "live" for live trading

# JVM Settings (optimized for automated trading)
JVM_MAX_MEM=768m
JVM_ARGS="-Xms256m -Xmx${JVM_MAX_MEM} -XX:+UseG1GC -Djava.awt.headless=false"

# Display settings for headless operation (if needed)
if [[ -z "$DISPLAY" ]]; then
    export DISPLAY=:99
    export XVFB_DISPLAY=:99
    log_message "No display detected, will use Xvfb for headless operation"
fi

# =============================================================================
# Functions
# =============================================================================

log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_DIR}/startup.log"
}

check_prerequisites() {
    log_message "Checking prerequisites..."
    
    # Check if Java is available
    if ! command -v java &> /dev/null; then
        log_message "ERROR: Java not found. Please install Java."
        exit 1
    fi
    
    # Check Java version
    JAVA_VERSION=$(java -version 2>&1 | head -n1 | cut -d'"' -f2)
    log_message "Using Java version: ${JAVA_VERSION}"
    
    # Check if IBC jar exists
    if [[ ! -f "${IBC_JAR}" ]]; then
        log_message "ERROR: IBC.jar not found at ${IBC_JAR}"
        exit 1
    fi
    
    # Check if config file exists
    if [[ ! -f "${CONFIG_FILE}" ]]; then
        log_message "ERROR: Config file not found at ${CONFIG_FILE}"
        exit 1
    fi
    
    # Check if TWS is installed (either directly or in versioned subdirectory)
    if [[ ! -d "${TWS_PATH}/jars" ]] && [[ ! -d "${TWS_PATH}/1039/jars" ]] && [[ ! -d "${TWS_PATH}/*/jars" ]]; then
        log_message "ERROR: TWS jars not found in ${TWS_PATH}"
        exit 1
    fi
    
    # Create log directory if it doesn't exist
    mkdir -p "${LOG_DIR}"
    
    log_message "Prerequisites check completed successfully"
}

cleanup() {
    log_message "Cleaning up processes..."
    # Kill any existing IBC/Gateway processes
    pkill -f "IBC.jar" 2>/dev/null || true
    pkill -f "ibgateway" 2>/dev/null || true
    pkill -f "ibcalpha.ibc.IbcGateway" 2>/dev/null || true
    stop_xvfb
    sleep 2
}

get_tws_version() {
    # Try to detect version from response.varfile
    local response_file="${TWS_PATH}/.install4j/response.varfile"
    if [[ -f "$response_file" ]]; then
        local version=$(grep "Trader Workstation" "$response_file" | sed -E 's/.*Trader Workstation ([0-9]+\.[0-9]+).*/\1/' | sed 's/\.//')
        if [[ -n "$version" ]]; then
            echo "$version"
            return
        fi
    fi
    
    # Fallback: Find TWS version by looking at installed jars directory
    local version_dirs=$(find "${TWS_PATH}" -maxdepth 2 -name "jars" -type d | head -1)
    if [[ -n "$version_dirs" ]]; then
        # Extract version from path like /path/to/tws/1019/jars or /path/to/tws/ibgateway/1019/jars
        local version=$(echo "$version_dirs" | sed -E 's|.*/([0-9]+)/jars|\1|')
        echo "$version"
    else
        # Default version if cannot detect
        echo "1039"
    fi
}

start_xvfb() {
    if [[ -n "$XVFB_DISPLAY" ]]; then
        log_message "Starting Xvfb for headless display on ${XVFB_DISPLAY}"
        xvfb-run -a -s "-screen 0 1024x768x24 -ac -nolisten tcp -dpi 96" \
            bash -c "export DISPLAY=${XVFB_DISPLAY}; echo 'Xvfb ready'" &
        XVFB_PID=$!
        echo ${XVFB_PID} > "${LOG_DIR}/xvfb.pid"
        sleep 2
        log_message "Xvfb started with PID: ${XVFB_PID}"
    fi
}

stop_xvfb() {
    if [[ -f "${LOG_DIR}/xvfb.pid" ]]; then
        XVFB_PID=$(cat "${LOG_DIR}/xvfb.pid")
        if kill -0 ${XVFB_PID} 2>/dev/null; then
            log_message "Stopping Xvfb (PID: ${XVFB_PID})"
            kill ${XVFB_PID} 2>/dev/null
            rm -f "${LOG_DIR}/xvfb.pid"
        fi
    fi
}

start_gateway() {
    log_message "Starting IB Gateway with IBC..."
    
    # Start Xvfb if needed
    start_xvfb
    
    # Detect TWS version
    local TWS_VERSION=$(get_tws_version)
    log_message "Detected TWS version: ${TWS_VERSION}"
    
    # Use IBC's proper startup script approach
    export TWS_MAJOR_VRSN="${TWS_VERSION}"
    export IBC_INI="${CONFIG_FILE}"
    export TRADING_MODE="${TRADING_MODE}"
    export TWOFA_TIMEOUT_ACTION="exit"
    export IBC_PATH="${IBC_PATH}"
    export TWS_PATH="${TWS_PATH}"
    export TWS_SETTINGS_PATH="${TWS_PATH}"
    export LOG_PATH="${LOG_DIR}"
    export APP="GATEWAY"
    
    # Start IBC using the proper method
    log_message "Starting IBC Gateway with version ${TWS_VERSION}"
    
    cd "${IBC_PATH}" || {
        log_message "ERROR: Failed to change to IBC directory"
        exit 1
    }
    
    # Use Xvfb if we're running headless
    if [[ -n "$XVFB_DISPLAY" ]]; then
        log_message "Using Xvfb display ${XVFB_DISPLAY} for headless operation"
        xvfb-run -a -s "-screen 0 1024x768x24 -ac -nolisten tcp -dpi 96" \
            "${IBC_PATH}/scripts/ibcstart.sh" \
            "${TWS_VERSION}" \
            --gateway \
            --tws-path="${TWS_PATH}" \
            --tws-settings-path="${TWS_PATH}" \
            --ibc-path="${IBC_PATH}" \
            --ibc-ini="${CONFIG_FILE}" \
            --java-path="/home/chris_s_dodd/.local/share/i4j_jres/Oda-jK0QgTEmVssfllLP/17.0.10.0.101-zulu_64/bin" \
            --mode="${TRADING_MODE}" \
            --on2fatimeout=exit 2>&1 | tee -a "${LOG_DIR}/gateway.log" &
    else
        # Use IBC's scripts directly with existing display
        "${IBC_PATH}/scripts/ibcstart.sh" \
            "${TWS_VERSION}" \
            --gateway \
            --tws-path="${TWS_PATH}" \
            --tws-settings-path="${TWS_PATH}" \
            --ibc-path="${IBC_PATH}" \
            --ibc-ini="${CONFIG_FILE}" \
            --java-path="/home/chris_s_dodd/.local/share/i4j_jres/Oda-jK0QgTEmVssfllLP/17.0.10.0.101-zulu_64/bin" \
            --mode="${TRADING_MODE}" \
            --on2fatimeout=exit 2>&1 | tee -a "${LOG_DIR}/gateway.log" &
    fi
    
    GATEWAY_PID=$!
    echo ${GATEWAY_PID} > "${LOG_DIR}/gateway.pid"
    
    log_message "IB Gateway started with PID: ${GATEWAY_PID}"
    
    # Wait for startup and check if process is still running
    log_message "Waiting for Gateway to initialize..."
    sleep 15
    
    if kill -0 ${GATEWAY_PID} 2>/dev/null; then
        log_message "Gateway process is running successfully"
        
        # Wait for API port to be available
        log_message "Waiting for API port to become available..."
        for i in {1..120}; do
            if ss -tln 2>/dev/null | grep -q ":4001 "; then
                log_message "API port 4001 is now available"
                return 0
            fi
            if [[ $i -eq 120 ]]; then
                log_message "WARNING: API port 4001 not detected after 240 seconds"
                return 1
            fi
            sleep 2
        done
        
    else
        log_message "ERROR: Gateway process failed to start"
        return 1
    fi
}

show_status() {
    if [[ -f "${LOG_DIR}/gateway.pid" ]]; then
        GATEWAY_PID=$(cat "${LOG_DIR}/gateway.pid")
        if kill -0 ${GATEWAY_PID} 2>/dev/null; then
            log_message "Gateway is running (PID: ${GATEWAY_PID})"
            
            # Check if API port is listening
            if netstat -tln 2>/dev/null | grep -q ":4001 " || ss -tln 2>/dev/null | grep -q ":4001 "; then
                log_message "API port 4001 is listening"
            else
                log_message "WARNING: API port 4001 is not listening"
            fi
        else
            log_message "Gateway process is not running"
        fi
    else
        log_message "No gateway PID file found"
    fi
}

# =============================================================================
# Main Script
# =============================================================================

case "${1:-start}" in
    start)
        log_message "=== Starting IB Gateway Setup ==="
        check_prerequisites
        cleanup
        start_gateway
        show_status
        log_message "=== Gateway startup completed ==="
        ;;
    stop)
        log_message "=== Stopping IB Gateway ==="
        cleanup
        log_message "=== Gateway stopped ==="
        ;;
    status)
        show_status
        ;;
    restart)
        log_message "=== Restarting IB Gateway ==="
        cleanup
        check_prerequisites
        start_gateway
        show_status
        log_message "=== Gateway restart completed ==="
        ;;
    *)
        echo "Usage: $0 {start|stop|status|restart}"
        echo "  start   - Start the IB Gateway"
        echo "  stop    - Stop the IB Gateway"
        echo "  status  - Show gateway status"
        echo "  restart - Restart the IB Gateway"
        exit 1
        ;;
esac

# Keep script running if started in foreground
if [[ "${1:-start}" == "start" ]] && [[ -t 1 ]]; then
    log_message "Gateway is running. Press Ctrl+C to stop."
    trap 'cleanup; exit 0' INT TERM
    tail -f "${LOG_DIR}/gateway.log" 2>/dev/null || sleep infinity
fi