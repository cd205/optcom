# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Automated options trading system built on Apache Airflow with Interactive Brokers Gateway integration. The system scrapes options data, validates contracts, manages IB Gateway connections with 2FA handling, and monitors trading strategies.

## Core Architecture

### Three-Layer System

1. **IBC Gateway Layer** (`ibc-setup/`)
   - Manages dual IB Gateway instances (paper trading on port 4002, live on port 4001)
   - Handles 2FA authentication with automatic retry logic
   - Uses IBC (Interactive Brokers Controller) for headless automation
   - Separate settings directories for paper and live accounts

2. **Airflow Workflow Layer** (`airflow_project/`)
   - **Main Trading Workflow** (manual trigger): 5-step linear DAG: check data → scrape → validate → start gateways → monitor with snapshots
   - Step 5 integrates market snapshots every 30 minutes while trading monitor runs
   - Implements smart data freshness checks to skip scraping if data exists
   - Enhanced 2FA retry mechanism with 90-minute timeout and 3-minute intervals
   - Non-blocking contract validation step

3. **Database Layer** (`database/`)
   - Supports both PostgreSQL (production) and SQLite (development)
   - Unified `DatabaseConfig` and `DatabaseConnection` classes
   - Credentials loaded from secure `config/credentials.json` (git-ignored)

### Key Integration Points

- **IBKR Integration** (`monitor/ibkr_integration.py`): IBAPIWrapper and IBKRDataProvider handle market data and contract validation
- **Gateway Utils** (`airflow_project/scripts/ib_gateway_utils.py`): IBGatewayManager orchestrates gateway lifecycle with smart status polling
- **Database Config** (`database/database_config.py`): Centralized connection management with automatic credential loading

## Common Commands

### Airflow Workflow Management

All commands run from `airflow_project/` directory:

```bash
# Start complete 5-step workflow
make start

# Check current workflow step status
make status

# Stop everything (workflow + gateways)
make stop

# Full restart
make restart
```

### Individual Step Debugging

```bash
make step1    # Check for today's data
make step2    # Run options scraper (10-15 min)
make step3    # Verify records written
make step4    # Start IB gateways (up to 15 min for 2FA)
make step5    # Trading monitor with snapshots every 30 min
```

### Gateway Management

From `ibc-setup/` directory:

```bash
# Start both paper and live gateways
./start-dual-gateway.sh start

# Check gateway status with API port verification
./start-dual-gateway.sh status

# Stop all gateways
./start-dual-gateway.sh stop

# Test API connections
./test_both_connections.py
```

Or from `airflow_project/`:

```bash
make gateway-status
make gateway-start
make gateway-stop
```

### Market Snapshots

```bash
# Test market snapshots (standalone - no Airflow)
make snapshots-test
```

Market snapshots are captured automatically during Step 5 of the main workflow:
- Snapshots taken every 30 minutes while the trading monitor runs
- Only runs when the main workflow is active (triggered by `make start`)
- Integrated into Step 5 - no separate DAG needed

Data captured:
- Current positions from IBKR
- Market values and unrealized P&L
- Individual option leg data
- Time-series snapshots in `market_snapshots` table

### Service Management (Production)

```bash
# Check systemd service status
sudo systemctl status trading-workflow.service

# View service logs
sudo journalctl -u trading-workflow.service -f

# Restart service
sudo systemctl restart trading-workflow.service
```

## Critical Implementation Details

### 2FA Handling

The system implements sophisticated 2FA retry logic:
- Initial gateway startup with 15-minute polling at 30-second intervals
- Enhanced retry mode: 90-minute total timeout with 3-minute retry intervals
- Automatic gateway restart to trigger new 2FA notifications if no response
- Paper gateway can proceed independently if live gateway 2FA times out

Implementation: `IBGatewayManager.start_gateways_with_2fa_retry()` and `monitor_2fa_with_retry()`

### Data Freshness Logic

Step 1 queries database for records with `scrape_date = today`:
- If found → skip steps 2 and 2.5, proceed to step 4
- If not found → run scraper in step 2

This prevents redundant scraping on workflow restarts.

### Contract Validation

Step 2.5 validates options contracts against IBKR and corrects expiry dates:
- Non-blocking: errors logged but don't fail workflow
- Requires paper gateway running on port 4002
- Updates `options_expiry_date` field for scraped contracts

### Database Connection Pattern

Always use centralized database utilities:

```python
from database.database_config import DatabaseConnection

db = DatabaseConnection()
with db.get_connection() as conn:
    cursor = db.get_cursor(conn)
    # execute queries
```

Credentials automatically loaded from `config/credentials.json` with fallback to environment variables.

### Gateway Port Assignments

- Port 4002: Paper trading gateway (used by trading monitor and market snapshots)
- Port 4001: Live trading gateway
- Separate settings directories maintain independent sessions

### Market Snapshots Architecture

Market snapshots are integrated into Step 5 of the main trading workflow:
- **Schedule**: Every 30 minutes during Step 5 execution (trading monitor loop)
- **Dependencies**: Requires paper gateway (port 4002) to be running (ensured by Step 4)
- **Behavior**: Gracefully handles errors without stopping the trading monitor
- **Data Flow**: IBKR positions → match with `option_strategies` → write to `ibkr_positions` and `market_snapshots`
- **Tables**:
  - Reads: `option_strategies` (active/order placed positions)
  - Writes: `ibkr_positions` (UPSERT on conflict)
  - Writes: `market_snapshots` (time-series inserts)

Implementation: `airflow_project/scripts/market_snapshots.py` (called from Step 5 in `simple_trading_workflow.py`)

## Security Requirements

**NEVER commit these files:**
- `config/credentials.json` - Contains all sensitive credentials
- `.env*` files
- `*.key`, `*.pem` files
- Database exports

All credentials managed through `config/credentials_loader.py` with automatic loading.

## Important File Locations

- Main workflow DAG: `airflow_project/dags/simple_trading_workflow.py`
- Market snapshots script: `airflow_project/scripts/market_snapshots.py`
- Gateway startup: `ibc-setup/start-dual-gateway.sh`
- Gateway utils: `airflow_project/scripts/ib_gateway_utils.py`
- Database config: `database/database_config.py`
- IBKR integration: `monitor/ibkr_integration.py`
- Workflow manager: `airflow_project/scripts/workflow_manager.py`

## Logging Locations

- Airflow logs: `airflow_project/logs/`
- Gateway logs: `ibc-setup/logs/paper-gateway.log` and `ibc-setup/logs/live-gateway.log`
- Dual startup log: `ibc-setup/logs/dual-startup.log`
- Service logs: `sudo journalctl -u trading-workflow.service`
- Workflow startup: `trading-workflow-startup.log`

## Testing

```bash
# Test database connection
python setup_credentials.py

# Test gateway connections
cd ibc-setup && ./test_both_connections.py

# Test individual workflow step
cd airflow_project && make step1

# Test market snapshots (standalone)
cd airflow_project && make snapshots-test
```

## Environment Setup

Required environment variable (defaults to PostgreSQL):
```bash
export DB_TYPE=postgresql  # or sqlite
export AIRFLOW_HOME=/path/to/airflow_project
```

Airflow database location: `airflow_project/airflow.db`
