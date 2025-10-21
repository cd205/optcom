# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an automated options trading system that scrapes options strategies (Bear Call and Bull Put spreads), stores them in a database, and executes trades through Interactive Brokers TWS/Gateway. The system uses Apache Airflow to orchestrate a 5-step workflow and supports both SQLite (development) and PostgreSQL (production) databases.

## Workflow Architecture

The system follows a **linear 5-step workflow** orchestrated by Airflow:

1. **Check Data**: Query database for today's scraped data. If found, skip to Step 4. If not found, proceed to Step 2.
2. **Run Scraper**: Scrape options strategies from optionrecom.com using Selenium. Stores records with unique trade IDs (generated using coolname library).
3. **Verify Records**: Confirm scraper successfully wrote records to database.
4. **Start Gateways**: Launch IB Gateway instances (paper + live) and wait for 2FA authentication (up to 15 minutes).
5. **Trading Monitor**: Execute trading logic using the paper trading port (4002), placing vertical spread orders.

**Key architectural decision**: The workflow uses simple linear dependencies (`step1 >> step2 >> step3 >> step4 >> step5`) with conditional logic inside tasks, rather than Airflow branching operators. This makes debugging easier.

## Database Architecture

The system uses a **database abstraction layer** ([database/database_config.py](database/database_config.py)) that supports:
- **PostgreSQL** (production): GCP Cloud SQL with connection pooling
- **SQLite** (fallback): Local file-based database

Database selection is controlled by `DB_TYPE` environment variable. The abstraction layer automatically handles dialect differences between PostgreSQL and SQLite.

**Credentials Management**: Uses a secure credentials loader ([config/credentials_loader.py](config/credentials_loader.py)) that reads from GCP Secret Manager or local encrypted credentials file, then falls back to environment variables if unavailable.

## IBC Gateway Management

Interactive Brokers gateways are managed through [ibc-setup/](ibc-setup/) which contains:
- Separate configurations for **paper** and **live** trading gateways
- Port assignments: Paper (4002), Live (4001)
- Auto-generated config files using [ibc-setup/generate_configs.py](ibc-setup/generate_configs.py)
- Gateway lifecycle managed by [airflow_project/scripts/ib_gateway_utils.py](airflow_project/scripts/ib_gateway_utils.py)

The system waits for 2FA authentication on the live gateway with smart polling (checks every 15 seconds, timeout after 15 minutes).

## Development Commands

### Workflow Management (from airflow_project/)

```bash
cd airflow_project

# Start complete workflow
make start

# Check status of current run
make status

# Stop everything (workflow + gateways)
make stop

# Full restart
make restart
```

### Individual Step Debugging

```bash
# Run individual steps for debugging
make step1          # Check data
make step2          # Run scraper (~10-15 min)
make step3          # Verify records
make step4          # Start gateways (~15 min with 2FA)
make step5          # Trading monitor (5 min test)
make step5-full     # Trading monitor (2 hour run)
```

### Gateway Management

```bash
make gateway-status  # Check if gateways are running
make gateway-start   # Start both gateways
make gateway-stop    # Stop both gateways
```

### Testing

```bash
# Test database migration and compatibility
python test_migration.py

# Test IB connections
cd ibc-setup
./test_both_connections.py
```

### Environment Setup

```bash
# Install Python dependencies
pip install -r requirements.txt

# For Airflow-specific dependencies
pip install -r airflow_project/requirements-airflow.txt

# Configure environment
cp .env.example .env
# Edit .env with your database credentials and IB credentials
```

## Key Files and Their Roles

- [airflow_project/dags/simple_trading_workflow.py](airflow_project/dags/simple_trading_workflow.py): Main DAG definition with 5 workflow steps
- [airflow_project/scripts/options_scraper.py](airflow_project/scripts/options_scraper.py): Selenium-based web scraper for options data
- [airflow_project/scripts/trading_monitor.py](airflow_project/scripts/trading_monitor.py): Trading execution logic and order placement
- [airflow_project/scripts/ib_gateway_utils.py](airflow_project/scripts/ib_gateway_utils.py): IB Gateway lifecycle management
- [database/database_config.py](database/database_config.py): Database abstraction layer supporting PostgreSQL/SQLite
- [monitor/ibkr_integration.py](monitor/ibkr_integration.py): Interactive Brokers API integration using ib_insync
- [monitor/vertical_spread_order.py](monitor/vertical_spread_order.py): Vertical spread order construction and placement

## Important Configuration Details

### Trade ID Generation
The scraper generates unique trade IDs using the `coolname` library, creating memorable names like "happy-dolphin-42". These IDs are stored in the database and used to track individual trades.

### Database Tables
The main table is `option_strategies` with columns including:
- `ticker`, `strategy_type` (Bear Call/Bull Put)
- `short_strike`, `long_strike`, `expiry_date`
- `trade_id` (unique identifier)
- `scrape_date`, `scrape_time`
- `expiry_date_as_scrapped` (original scraped date before validation)

### Contract Validation
Step 2.5 validates options contracts against IB's API and corrects expiry dates when they don't match valid trading dates. This is a non-blocking step that improves data quality but won't fail the workflow if it encounters errors.

## Systemd Service (Production)

The project can run as a systemd service (see [service-commands.md](service-commands.md)):

```bash
# Service management
sudo systemctl start trading-workflow.service
sudo systemctl status trading-workflow.service
sudo systemctl stop trading-workflow.service

# View logs
sudo journalctl -f -u trading-workflow.service
```

## Migration Notes

This project was migrated from SQLite to PostgreSQL. See [README_MIGRATION.md](README_MIGRATION.md) for:
- Database migration procedures
- GCP Cloud SQL setup instructions
- Testing both database backends
- Deployment with Docker

## Working with Airflow

```bash
# Set Airflow home (required for all Airflow commands)
export AIRFLOW_HOME=/home/cdodd/optcom/airflow_project

# Start Airflow standalone (includes webserver + scheduler)
airflow standalone &

# Trigger DAG manually
airflow dags trigger simple_trading_workflow

# Check DAG status
airflow dags list-runs -d simple_trading_workflow

# View task logs
airflow tasks logs simple_trading_workflow step1_check_data <execution_date>
```

The Airflow webserver runs on `http://localhost:8080` with health check endpoint at `/health`.
