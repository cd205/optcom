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