# IBC Configuration Management

This document explains how to manage IBC configurations using the centralized credentials system.

## Overview

The IBC setup now uses the centralized `config/credentials.json` file for all authentication credentials. Configuration files are auto-generated from this JSON file to ensure consistency and security.

## Credentials Structure

Add your IBKR credentials to `config/credentials.json`:

```json
{
  "ibkr": {
    "paper": {
      "username": "YOUR_PAPER_USERNAME",
      "password": "YOUR_PAPER_PASSWORD"
    },
    "live": {
      "username": "YOUR_LIVE_USERNAME", 
      "password": "YOUR_LIVE_PASSWORD"
    }
  }
}
```

## Configuration Files

### Generated Files (Do NOT edit manually):
- `config/config-paper.ini` - Paper trading configuration
- `config/config-live.ini` - Live trading configuration  
- `config/config.ini` - Symbolic link to current default config

### Source Files:
- `config/credentials.json` - Master credentials file
- `generate_configs.py` - Configuration generator script
- `update_configs.sh` - Configuration management script

## Usage

### 1. Add Your Credentials

Edit `config/credentials.json` and replace the placeholder credentials:

```json
{
  "ibkr": {
    "paper": {
      "username": "your_paper_username",
      "password": "your_paper_password"
    },
    "live": {
      "username": "your_live_username", 
      "password": "your_live_password"
    }
  }
}
```

### 2. Generate Configuration Files

```bash
# Generate configs from JSON
./update_configs.sh --generate

# Or use the Python script directly
python3 generate_configs.py
```

### 3. Switch Between Trading Modes

```bash
# Use paper trading (default)
./update_configs.sh --mode paper

# Use live trading
./update_configs.sh --mode live
```

### 4. Check Current Status

```bash
# Show current configuration status
./update_configs.sh
```

## Security Features

- **Centralized credentials**: All credentials in one secure JSON file
- **Auto-generation**: Config files regenerated from source, preventing manual errors
- **Mode separation**: Clear separation between paper and live trading configs
- **Safe defaults**: Paper trading set as default, live trading requires explicit switch

## Gateway Startup

After configuring credentials:

```bash
# Start both paper and live gateways
./start-dual-gateway.sh start

# Start only paper gateway
./start-gateway.sh start paper

# Start only live gateway  
./start-gateway.sh start live

# Check status
./start-dual-gateway.sh status
```

## Configuration Differences

### Paper Trading Config:
- `TradingMode=paper`
- `AcceptNonBrokerageAccountWarning=yes` (auto-accept paper warning)
- Uses paper trading credentials

### Live Trading Config:
- `TradingMode=live`
- `AcceptNonBrokerageAccountWarning=no` (manual confirmation required)
- Uses live trading credentials

## Troubleshooting

### Missing Credentials
If you see placeholder usernames like `YOUR_PAPER_USERNAME`:
1. Edit `config/credentials.json` with real credentials
2. Run `./update_configs.sh --generate`

### Wrong Trading Mode
If gateway starts in wrong mode:
1. Check which config is active: `./update_configs.sh`
2. Switch mode: `./update_configs.sh --mode [paper|live]`
3. Restart gateway

### Authentication Failures
1. Verify credentials in `config/credentials.json`
2. Regenerate configs: `./update_configs.sh --generate`
3. Check for special characters that need escaping
4. Ensure 2FA is properly configured in IBKR account

## File Permissions

Ensure credentials file has proper permissions:
```bash
chmod 600 config/credentials.json  # Only owner can read/write
```

## Backup

Always backup your credentials file:
```bash
cp config/credentials.json config/credentials.json.backup
```