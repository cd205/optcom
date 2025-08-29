#!/bin/bash

# Dual IB Gateway Startup Script - Paper and Live Accounts
# Following IBC best practices for automated trading systems

# =============================================================================
# Configuration Variables
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IBC_PATH="${SCRIPT_DIR}/ibc"
TWS_PATH="${SCRIPT_DIR}/tws"
CONFIG_PATH="${SCRIPT_DIR}/config"
LOG_DIR="${SCRIPT_DIR}/logs"

# Account configurations
PAPER_CONFIG="${CONFIG_PATH}/config-paper.ini"
LIVE_CONFIG="${CONFIG_PATH}/config-live.ini"

# Settings directories (separate for each account)
PAPER_SETTINGS="${TWS_PATH}/paper-settings"
LIVE_SETTINGS="${TWS_PATH}/live-settings"

# Create separate settings directories
mkdir -p "${PAPER_SETTINGS}" "${LIVE_SETTINGS}"

# =============================================================================
# Functions
# =============================================================================

log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_DIR}/dual-startup.log"
}

get_tws_version() {
    local response_file="${TWS_PATH}/.install4j/response.varfile"
    if [[ -f "$response_file" ]]; then
        local version=$(grep "Trader Workstation" "$response_file" | sed -E 's/.*Trader Workstation ([0-9]+\.[0-9]+).*/\1/' | sed 's/\.//')
        if [[ -n "$version" ]]; then
            echo "$version"
            return
        fi
    fi
    echo "1039"
}

start_account() {
    local account_type="$1"
    local config_file="$2" 
    local settings_path="$3"
    local api_port="$4"
    
    log_message "Starting ${account_type} account Gateway..."
    
    # Display settings for headless operation
    if [[ -z "$DISPLAY" ]]; then
        export DISPLAY=:99
        log_message "Using virtual display :99 for ${account_type} account"
    fi
    
    local TWS_VERSION=$(get_tws_version)
    log_message "Using TWS version: ${TWS_VERSION} for ${account_type}"
    
    # Set environment variables for this account
    export TWS_MAJOR_VRSN="${TWS_VERSION}"
    export IBC_INI="${config_file}"
    export TRADING_MODE="${account_type}"
    export TWOFA_TIMEOUT_ACTION="restart"
    export IBC_PATH="${IBC_PATH}"
    export TWS_PATH="${TWS_PATH}"
    export TWS_SETTINGS_PATH="${settings_path}"
    export LOG_PATH="${LOG_DIR}"
    export APP="GATEWAY"
    
    # Start this account's Gateway with Xvfb
    log_message "Starting ${account_type} Gateway on port ${api_port}"
    
    xvfb-run -a -s "-screen 0 1024x768x24 -ac -nolisten tcp -dpi 96" \
        "${IBC_PATH}/scripts/ibcstart.sh" \
        "${TWS_VERSION}" \
        --gateway \
        --tws-path="${TWS_PATH}" \
        --tws-settings-path="${settings_path}" \
        --ibc-path="${IBC_PATH}" \
        --ibc-ini="${config_file}" \
        --mode="${account_type}" \
        --on2fatimeout=restart 2>&1 | tee -a "${LOG_DIR}/${account_type}-gateway.log" &
    
    local GATEWAY_PID=$!
    echo ${GATEWAY_PID} > "${LOG_DIR}/${account_type}-gateway.pid"
    
    log_message "${account_type} Gateway started with PID: ${GATEWAY_PID}"
    
    # Wait for this account to initialize
    log_message "Waiting for ${account_type} Gateway to initialize..."
    sleep 20
    
    if kill -0 ${GATEWAY_PID} 2>/dev/null; then
        log_message "${account_type} Gateway process is running"
        
        # Wait for API port
        log_message "Waiting for ${account_type} API port ${api_port}..."
        for i in {1..60}; do
            if ss -tln 2>/dev/null | grep -q ":${api_port} "; then
                log_message "✅ ${account_type} API port ${api_port} is available"
                return 0
            fi
            sleep 3
        done
        log_message "⚠️ ${account_type} API port ${api_port} not detected"
        return 1
    else
        log_message "❌ ${account_type} Gateway failed to start"
        return 1
    fi
}

start_both_accounts() {
    log_message "=== Starting Both Paper and Live Accounts ==="
    
    # Start paper account first (port 4002)
    log_message "Step 1: Starting Paper Trading Account"
    if start_account "paper" "${PAPER_CONFIG}" "${PAPER_SETTINGS}" "4002"; then
        log_message "✅ Paper account ready on port 4002"
    else
        log_message "❌ Paper account failed - continuing with live account anyway"
    fi
    
    # Wait between account startups to avoid conflicts
    log_message "Waiting 30 seconds before starting live account..."
    sleep 30
    
    # Start live account second (port 4001)
    log_message "Step 2: Starting Live Trading Account"
    if start_account "live" "${LIVE_CONFIG}" "${LIVE_SETTINGS}" "4001"; then
        log_message "✅ Live account ready on port 4001"
    else
        log_message "❌ Live account failed"
    fi
    
    log_message "=== Dual Gateway Startup Complete ==="
    show_status
}

stop_all() {
    log_message "Stopping all Gateway instances..."
    
    # Kill all IBC/Gateway processes
    pkill -f "ibcalpha.ibc.IbcGateway" 2>/dev/null || true
    pkill -f "IBC.jar" 2>/dev/null || true
    pkill -f "ibgateway" 2>/dev/null || true
    
    # Clean up PID files
    rm -f "${LOG_DIR}/paper-gateway.pid" "${LOG_DIR}/live-gateway.pid"
    
    log_message "All Gateway instances stopped"
}

show_status() {
    log_message "=== Gateway Status ==="
    
    # Check paper account by process pattern and port
    local PAPER_PID=$(pgrep -f "java.*paper.*IbcGateway" | head -1)
    if [[ -n "$PAPER_PID" ]]; then
        log_message "📊 Paper Gateway: Running (PID: ${PAPER_PID})"
        # Update PID file for consistency
        echo "$PAPER_PID" > "${LOG_DIR}/paper-gateway.pid"
        if ss -tln 2>/dev/null | grep -q ":4002 "; then
            log_message "   ✅ API Port 4002: Listening"
        else
            log_message "   ❌ API Port 4002: Not listening"
        fi
    else
        log_message "📊 Paper Gateway: Not running"
        # Clean up stale PID file
        rm -f "${LOG_DIR}/paper-gateway.pid"
    fi
    
    # Check live account by process pattern and port
    local LIVE_PID=$(pgrep -f "java.*live.*IbcGateway" | head -1)
    if [[ -n "$LIVE_PID" ]]; then
        log_message "💰 Live Gateway: Running (PID: ${LIVE_PID})"
        # Update PID file for consistency
        echo "$LIVE_PID" > "${LOG_DIR}/live-gateway.pid"
        if ss -tln 2>/dev/null | grep -q ":4001 "; then
            log_message "   ✅ API Port 4001: Listening"
        else
            log_message "   ❌ API Port 4001: Not listening"
        fi
    else
        log_message "💰 Live Gateway: Not running"
        # Clean up stale PID file
        rm -f "${LOG_DIR}/live-gateway.pid"
    fi
}

restart_account() {
    local account_type="$1"
    
    if [[ "$account_type" == "paper" ]]; then
        log_message "Restarting paper account only..."
        pkill -f "paper.*ibcalpha.ibc.IbcGateway" 2>/dev/null || true
        rm -f "${LOG_DIR}/paper-gateway.pid"
        sleep 5
        start_account "paper" "${PAPER_CONFIG}" "${PAPER_SETTINGS}" "4002"
    elif [[ "$account_type" == "live" ]]; then
        log_message "Restarting live account only..."
        pkill -f "live.*ibcalpha.ibc.IbcGateway" 2>/dev/null || true
        rm -f "${LOG_DIR}/live-gateway.pid"
        sleep 5
        start_account "live" "${LIVE_CONFIG}" "${LIVE_SETTINGS}" "4001"
    else
        log_message "Invalid account type. Use 'paper' or 'live'"
        exit 1
    fi
}

# =============================================================================
# Main Script
# =============================================================================

case "${1:-start}" in
    start)
        start_both_accounts
        ;;
    stop)
        stop_all
        ;;
    status)
        show_status
        ;;
    restart)
        if [[ -n "$2" ]]; then
            restart_account "$2"
        else
            log_message "Restarting both accounts..."
            stop_all
            sleep 5
            start_both_accounts
        fi
        ;;
    paper)
        start_account "paper" "${PAPER_CONFIG}" "${PAPER_SETTINGS}" "4002"
        ;;
    live)
        start_account "live" "${LIVE_CONFIG}" "${LIVE_SETTINGS}" "4001"
        ;;
    *)
        echo "Usage: $0 {start|stop|status|restart [paper|live]|paper|live}"
        echo ""
        echo "Commands:"
        echo "  start           - Start both paper and live accounts"
        echo "  stop            - Stop all Gateway instances"
        echo "  status          - Show status of both accounts"
        echo "  restart         - Restart both accounts"
        echo "  restart paper   - Restart only paper account"
        echo "  restart live    - Restart only live account"
        echo "  paper           - Start only paper account"
        echo "  live            - Start only live account"
        echo ""
        echo "API Connections:"
        echo "  Paper Trading:  localhost:4002"
        echo "  Live Trading:   localhost:4001"
        exit 1
        ;;
esac