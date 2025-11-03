#!/bin/bash

# Update IBC configuration files from credentials.json
# This script regenerates the INI files and can switch between paper/live configs

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${SCRIPT_DIR}/config"

show_help() {
    echo "Update IBC Configuration from credentials.json"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help     Show this help message"
    echo "  -m, --mode     Set default mode (paper|live)"
    echo "  -g, --generate Generate config files from credentials.json"
    echo ""
    echo "Examples:"
    echo "  $0 --generate           # Generate configs from JSON"
    echo "  $0 --mode paper         # Set paper trading as default"
    echo "  $0 --mode live          # Set live trading as default"
    echo "  $0 -g -m paper          # Generate configs and set paper as default"
}

generate_configs() {
    echo "🔧 Generating configuration files from credentials.json..."
    python3 "${SCRIPT_DIR}/generate_configs.py"
}

set_default_mode() {
    local mode="$1"
    
    if [[ "$mode" != "paper" && "$mode" != "live" ]]; then
        echo "❌ Invalid mode: $mode. Must be 'paper' or 'live'"
        return 1
    fi
    
    local config_file="${CONFIG_DIR}/config-${mode}.ini"
    local default_config="${CONFIG_DIR}/config.ini"
    
    if [[ ! -f "$config_file" ]]; then
        echo "❌ Configuration file not found: $config_file"
        echo "Run with --generate first to create configuration files"
        return 1
    fi
    
    # Remove existing symlink/file
    rm -f "$default_config"
    
    # Create new symlink
    ln -sf "config-${mode}.ini" "$default_config"
    
    echo "✅ Default configuration set to: $mode trading"
    echo "   config.ini → config-${mode}.ini"
}

# Parse command line arguments
GENERATE=false
MODE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -g|--generate)
            GENERATE=true
            shift
            ;;
        -m|--mode)
            MODE="$2"
            shift 2
            ;;
        *)
            echo "❌ Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Execute requested actions
if [[ "$GENERATE" == "true" ]]; then
    generate_configs
fi

if [[ -n "$MODE" ]]; then
    set_default_mode "$MODE"
fi

# If no arguments provided, show current status
if [[ "$GENERATE" == "false" && -z "$MODE" ]]; then
    echo "🔍 Current IBC Configuration Status:"
    echo ""
    
    # Check if config files exist
    echo "📁 Configuration files:"
    for config in "config.ini" "config-paper.ini" "config-live.ini"; do
        config_path="${CONFIG_DIR}/${config}"
        if [[ -f "$config_path" ]]; then
            if [[ -L "$config_path" ]]; then
                target=$(readlink "$config_path")
                echo "   ✅ $config → $target"
            else
                echo "   ✅ $config (file)"
            fi
        else
            echo "   ❌ $config (missing)"
        fi
    done
    
    echo ""
    echo "💡 Usage:"
    echo "   $0 --generate          # Generate configs from credentials.json"
    echo "   $0 --mode paper        # Switch to paper trading"
    echo "   $0 --mode live         # Switch to live trading"
fi