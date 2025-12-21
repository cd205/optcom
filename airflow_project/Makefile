# Simple Trading Workflow Commands
# ================================

# Set environment
export AIRFLOW_HOME := $(PWD)

# Main workflow commands
.PHONY: start stop status restart

start:
	@echo "🚀 Starting Simple Trading Workflow..."
	cd scripts && python workflow_manager.py start

stop:
	@echo "🛑 Stopping Everything..."
	cd scripts && python workflow_manager.py stop

status:
	@echo "🔍 Checking Workflow Status..."
	cd scripts && python workflow_manager.py status

restart:
	@echo "🔄 Full Restart..."
	cd scripts && python workflow_manager.py restart

# Individual step debugging
.PHONY: step1 step2 step3 step4 step5

step1:
	@echo "🔍 Running Step 1: Check Data..."
	cd scripts && python run_individual_steps.py 1

step2:
	@echo "🚀 Running Step 2: Scraper..."
	cd scripts && python run_individual_steps.py 2

step3:
	@echo "✅ Running Step 3: Verify Records..."
	cd scripts && python run_individual_steps.py 3

step4:
	@echo "🚪 Running Step 4: Start Gateways..."
	cd scripts && python run_individual_steps.py 4

step5:
	@echo "📊 Running Step 5: Trading Monitor (5 min test)..."
	cd scripts && python run_individual_steps.py 5 --runtime 300

step5-full:
	@echo "📊 Running Step 5: Trading Monitor (2 hours)..."
	cd scripts && python run_individual_steps.py 5 --runtime 7200

# Utility commands
.PHONY: gateway-status gateway-start gateway-stop airflow-start snapshots-test snapshots-status

gateway-status:
	@echo "🚪 Gateway Status..."
	cd scripts && python ib_gateway_utils.py status

gateway-start:
	@echo "🚪 Starting Gateways..."
	cd scripts && python ib_gateway_utils.py start

gateway-stop:
	@echo "🚪 Stopping Gateways..."
	cd scripts && python ib_gateway_utils.py stop

airflow-start:
	@echo "🌪️ Starting Airflow..."
	@export AIRFLOW_HOME=$(PWD) && airflow standalone &

snapshots-test:
	@echo "📸 Testing Market Snapshots (standalone)..."
	cd scripts && python market_snapshots.py

snapshots-status:
	@echo "📸 Checking Market Snapshots DAG Status..."
	@export AIRFLOW_HOME=$(PWD) && airflow dags show market_snapshots

# EOD Data Collection commands
.PHONY: eod-collect eod-collect-manual eod-status eod-verify eod-logs eod-test

eod-collect:
	@echo "📊 Triggering EOD Data Collection DAG..."
	@export AIRFLOW_HOME=$(PWD) && airflow dags trigger eod_data_collection_workflow

eod-collect-manual:
	@echo "📊 Running EOD Collection Manually (bypassing Airflow)..."
	cd scripts && python eod_data_collection.py

eod-status:
	@echo "📊 EOD DAG Status..."
	@export AIRFLOW_HOME=$(PWD) && airflow dags list-runs -d eod_data_collection_workflow --output table

eod-verify:
	@echo "✅ Verifying EOD Data Collection..."
	cd scripts && python verify_eod_data.py

eod-verify-week:
	@echo "✅ Verifying Last 7 Days of EOD Data..."
	cd scripts && python verify_eod_data.py --days 7

eod-logs:
	@echo "📋 EOD Collection Logs..."
	@export AIRFLOW_HOME=$(PWD) && airflow tasks logs eod_data_collection_workflow collect_eod_data latest || echo "No logs yet - DAG hasn't run"

eod-test:
	@echo "🧪 Testing EOD Collection (dry run with yesterday's date)..."
	cd scripts && python eod_data_collection.py --date $$(date -d "yesterday" +%Y-%m-%d) || python eod_data_collection.py --date $$(date -v-1d +%Y-%m-%d)

# Help
.PHONY: help

help:
	@echo "Simple Trading Workflow Commands"
	@echo "================================="
	@echo ""
	@echo "Main Commands:"
	@echo "  make start        - Start the complete 5-step workflow"
	@echo "  make stop         - Stop everything (workflow + gateways)"
	@echo "  make status       - Check which step is currently running"
	@echo "  make restart      - Full stop and restart"
	@echo ""
	@echo "Individual Steps (for debugging):"
	@echo "  make step1        - Check for today's data"
	@echo "  make step2        - Run options scraper"
	@echo "  make step3        - Verify records were written"
	@echo "  make step4        - Start IB gateways"
	@echo "  make step5        - Run trading monitor (5 min test)"
	@echo "  make step5-full   - Run trading monitor (2 hours)"
	@echo ""
	@echo "Utilities:"
	@echo "  make gateway-status - Check gateway status only"
	@echo "  make gateway-start  - Start gateways only"
	@echo "  make gateway-stop   - Stop gateways only"
	@echo "  make airflow-start  - Start Airflow only"
	@echo ""
	@echo "Market Snapshots:"
	@echo "  make snapshots-test   - Test market snapshots (standalone)"
	@echo "  make snapshots-status - Check snapshots DAG status"
	@echo ""
	@echo "EOD Data Collection:"
	@echo "  make eod-collect        - Trigger EOD collection DAG"
	@echo "  make eod-collect-manual - Run EOD collection manually (bypass Airflow)"
	@echo "  make eod-status         - Check EOD DAG runs"
	@echo "  make eod-verify         - Verify today's EOD data"
	@echo "  make eod-verify-week    - Verify last 7 days of EOD data"
	@echo "  make eod-logs           - View EOD collection logs"
	@echo "  make eod-test           - Test EOD collection with yesterday's data"